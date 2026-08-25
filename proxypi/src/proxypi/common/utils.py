import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from pydantic import BaseModel
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

DataModel = TypeVar("DataModel", bound=BaseModel)


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


CoroResponse = TypeVar("CoroResponse")


async def run_with_spinner(
    coro: Awaitable[CoroResponse], description: str, timeout_in_seconds: int
) -> CoroResponse:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeRemainingColumn(),
        transient=True,  # disappears when complete
    ) as progress:
        task = progress.add_task(
            description,
            total=timeout_in_seconds,
        )

        async def update_progress():
            while not progress.finished:
                await asyncio.sleep(1)
                progress.advance(task, 1)

        updater = asyncio.create_task(update_progress())

        try:
            return await coro
        finally:
            updater.cancel()
            try:
                await updater
            except asyncio.CancelledError:
                pass
            progress.update(task, completed=timeout_in_seconds)
