import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Awaitable, ParamSpec, TypeVar, overload

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from proxypi.common.types import AsyncFunc, DataModel, PosInt

P = ParamSpec("P")
T = TypeVar("T")


def to_table(array: list[DataModel]) -> Table:
    table = Table()

    if not array:
        return table

    model_type = type(array[0])

    for field in model_type.model_fields:
        table.add_column(field)

    for item in array:
        table.add_row(
            *[
                str(getattr(item, field)) if getattr(item, field) is not None else ""
                for field in model_type.model_fields
            ]
        )

    return table


def print_table(table: Table) -> None:
    console = Console()
    console.print(table)


def run_with_spinner(description: str) -> Callable[[AsyncFunc], AsyncFunc]:
    def decorator(
        async_func: AsyncFunc,
    ) -> AsyncFunc:
        @wraps(async_func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            timeout = kwargs.get("timeout")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeRemainingColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task(
                    description,
                    total=timeout,
                )

                async def update_progress():
                    while not progress.finished:
                        await asyncio.sleep(1)
                        progress.advance(task, 1)

                updater = asyncio.create_task(update_progress())

                try:
                    return await async_func(*args, **kwargs)
                finally:
                    updater.cancel()
                    try:
                        await updater
                    except asyncio.CancelledError:
                        pass
                    progress.update(task, completed=timeout)

        return wrapper

    return decorator


async def gather_with_semaphore(
    *coros: Awaitable[T],
    concurrent_conn: PosInt,
) -> list[T]:
    """
    Does not support well cancellation through `Ctrl+C` because
    the coroutines are created before being received and therefore
    we get `RuntimeWarning: coroutine was never awaited`
    """

    sem = asyncio.Semaphore(concurrent_conn)

    async def run(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return await asyncio.gather(*[run(c) for c in coros])


class ThreeStateBarColumn(ProgressColumn):
    def __init__(self, width: int = 40):
        self.width = width
        super().__init__()

    def render(self, task: Task) -> Text:
        total = task.total or 1

        done = int(task.completed)
        running = int(task.fields.get("running", 0))
        waiting = int(task.fields.get("waiting", 0))

        done_width = round(self.width * done / total)
        running_width = round(self.width * running / total)

        # Make the segments add up exactly to `width`
        waiting_width = self.width - done_width - running_width

        bar = Text()

        bar.append("█" * done_width, style="green")
        bar.append("▓" * running_width, style="yellow")
        bar.append("░" * waiting_width, style="grey50")

        return bar


async def gather_with_progress(
    *coros: Awaitable[T],
    concurrent_conn: PosInt,
) -> list[T]:

    sem = asyncio.Semaphore(concurrent_conn)
    lock_progress = asyncio.Lock()

    with Progress(
        TextColumn("{task.description}"),
        ThreeStateBarColumn(width=40),
        TextColumn(
            "[green]{task.completed:.0f} done[/] "
            "[yellow]{task.fields[running]} running[/] "
            "[grey50]{task.fields[waiting]} waiting[/]"
        ),
        transient=True,
    ) as progress:
        task_id = progress.add_task(
            "Processing",
            total=len(coros),
            running=0,
            waiting=len(coros),
        )

        async def run(coro: Awaitable[T]) -> T:
            async with sem:
                async with lock_progress:
                    task = progress.tasks[task_id]
                    progress.update(
                        task_id,
                        running=task.fields["running"] + 1,
                        waiting=task.fields["waiting"] - 1,
                    )

                try:
                    return await coro
                finally:
                    async with lock_progress:
                        task = progress.tasks[task_id]
                        progress.update(
                            task_id,
                            advance=1,
                            running=task.fields["running"] - 1,
                        )

        return await asyncio.gather(*[run(c) for c in coros])
