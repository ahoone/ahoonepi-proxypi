import asyncio
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from proxypi.common.types import AsyncFunc, DataModel

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
