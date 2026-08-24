from typing import TypeVar

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

T = TypeVar("T", bound=BaseModel)


def to_table(array: list[T]) -> Table:
    table = Table()

    if not array:
        return table

    model_type = type(array[0])

    for field in model_type.model_fields:
        table.add_column(field)

    for object in array:
        table.add_row(
            *[
                str(getattr(object, field))
                if getattr(object, field) is not None
                else ""
                for field in model_type.model_fields
            ]
        )

    return table


def print_table(table: Table) -> None:
    console = Console()
    console.print(table)
