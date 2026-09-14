import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from proxypi.common.stdout import (
    drop_terminal_holder,
    run_on_stdout,
    set_terminal_holder,
)
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


def run_with_spinner(
    description: str,
) -> Callable[[AsyncFunc[P, T]], AsyncFunc[P, T]]:

    def decorator(
        async_func: AsyncFunc[P, T],
    ) -> AsyncFunc[P, T]:

        @run_on_stdout()
        @wraps(async_func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeRemainingColumn(),
                transient=True,
            ) as progress:
                set_terminal_holder(progress)

                timeout = kwargs.get("timeout") if "timeout" in kwargs else None
                if timeout is not None and not isinstance(timeout, float):
                    raise TypeError(
                        f"decorated coroutine `timeout` parameter is of wrong type: {type(timeout)}"
                    )

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
                    drop_terminal_holder()

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

    try:
        return await asyncio.gather(*[run(c) for c in coros])
    except asyncio.CancelledError:
        return []


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


async def __tracking_exe_coro(
    coro: Awaitable[T],
    progress: Progress,
    progress_lock: asyncio.Lock,
    task_id: TaskID,
) -> T:
    async with progress_lock:
        task = progress.tasks[task_id]
        progress.update(
            task_id,
            running=task.fields["running"] + 1,
            waiting=task.fields["waiting"] - 1,
        )

    try:
        return await coro
    finally:
        async with progress_lock:
            task = progress.tasks[task_id]
            progress.update(
                task_id,
                advance=1,
                running=task.fields["running"] - 1,
            )


async def gather_with_tracking(
    *coros: Awaitable[T],
    concurrent_conn: PosInt,
    progress: Progress,
    task_id: TaskID,
) -> list[T]:
    """
    Wraps `asyncio.gather` implementing semaphore and
    tracking into the given `rich.progress.Progress`
    the advancement.

    The progress should not be modified outside of
    the field of this method.
    """

    sem = asyncio.Semaphore(concurrent_conn)
    progress_lock = asyncio.Lock()

    async def run(coro: Awaitable[T]) -> T:
        async with sem:
            return await __tracking_exe_coro(coro, progress, progress_lock, task_id)

    try:
        return await asyncio.gather(*[run(c) for c in coros])
    except asyncio.CancelledError:
        return []


@run_on_stdout()
async def gather_with_progress(
    *coros: Awaitable[T],
    concurrent_conn: PosInt,
) -> list[T]:
    """
    There should be only one call at any time of this function.
    The progress bar must be suspendable in case of inputs for sudo.
    """

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
        set_terminal_holder(progress)

        try:
            task_id = progress.add_task(
                "Processing",
                total=len(coros),
                running=0,
                waiting=len(coros),
            )

            return await gather_with_tracking(
                *coros,
                concurrent_conn=concurrent_conn,
                progress=progress,
                task_id=task_id,
            )
        finally:
            drop_terminal_holder()
