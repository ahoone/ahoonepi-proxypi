from collections.abc import Awaitable, Callable
from typing import Annotated, ParamSpec, TypeVar

from pydantic import BaseModel, Field

from proxypi.common.constants import RANGE_PORTS
from proxypi.config import config

P = ParamSpec("P")
T = TypeVar("T")

AsyncFunc = Callable[P, Awaitable[T]]

DataModel = TypeVar("DataModel", bound=BaseModel)

# pydantic flavored, not compatible with typer
Port = Annotated[int, Field(ge=RANGE_PORTS[0], le=RANGE_PORTS[1])]
ProxyID = Annotated[int, Field(ge=2, le=config.network_size - 1)]
