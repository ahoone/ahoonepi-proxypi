from collections.abc import Awaitable, Callable
from typing import Annotated, ParamSpec, TypeVar

from pydantic import BaseModel, Field

P = ParamSpec("P")
T = TypeVar("T")

AsyncFunc = Callable[P, Awaitable[T]]

DataModel = TypeVar("DataModel", bound=BaseModel)

# pydantic flavored, not compatible with typer
Port = Annotated[int, Field(ge=0, le=2**16 - 1)]
