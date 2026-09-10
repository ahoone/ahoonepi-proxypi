import asyncio
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from functools import wraps
from typing import ClassVar, ParamSpec, TypeVar

from rich.console import Console
from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
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


class SuspendProgress:
    __progress_suspend_count: ClassVar[int] = 0
    __lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    __suspended_progress: Progress | None = None

    def __init__(self):
        self.progress = _active_progress

    async def __enter__(self):
        async with self.__lock:
            SuspendProgress.__progress_suspend_count += 1
            if (
                SuspendProgress.__progress_suspend_count == 1
                and self.progress is not None
            ):
                self.progress.stop()


# @contextmanager
# async def suspend_progress():
#     global

#     progress = _active_progress

#     async with :

#     if progress is not None:
#         progress.stop()
#     try:
#         yield
#     finally:
#         if progress is not None:
#             progress.start()


def run_with_spinner(description: str) -> Callable[[AsyncFunc], AsyncFunc]:
    """
    The progress bar must be suspendable in case of inputs for sudo.
    """

    def decorator(
        async_func: AsyncFunc,
    ) -> AsyncFunc:
        @wraps(async_func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            timeout = kwargs.get("timeout")
            global _active_progress

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeRemainingColumn(),
                transient=True,
            ) as progress:
                _active_progress = progress

                try:
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
                finally:
                    _active_progress = None

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

        done_width = round(self.width * done / total)
        running_width = round(self.width * running / total)

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
    """
    The progress bar must be suspendable in case of inputs for sudo.
    """

    sem = asyncio.Semaphore(concurrent_conn)
    lock_progress = asyncio.Lock()
    global _active_progress

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
        _active_progress = progress

        try:
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
        finally:
            _active_progress = None
