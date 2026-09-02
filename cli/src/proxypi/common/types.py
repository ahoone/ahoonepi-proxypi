from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Annotated, ParamSpec, TypeVar, override

from pydantic import BaseModel, Field

from proxypi.common.config import config
from proxypi.common.constants import RANGE_PORTS

P = ParamSpec("P")
T = TypeVar("T")

AsyncFunc = Callable[P, Awaitable[T]]

DataModel = TypeVar("DataModel", bound=BaseModel)

# pydantic flavored, not compatible with typer
Port = Annotated[int, Field(ge=RANGE_PORTS[0], le=RANGE_PORTS[1])]
ProxyID = Annotated[int, Field(ge=2, le=config.network_size - 1)]


class Dependency(ABC):
    @staticmethod
    @abstractmethod
    def _is_installed() -> bool: ...

    @staticmethod
    @abstractmethod
    def _is_meeting_min_version_required(min_version: tuple[int, ...]) -> bool: ...

    def is_satisfied(self, min_version: tuple[int, ...]) -> bool:
        return self._is_installed() and self._is_meeting_min_version_required(
            min_version
        )

    @staticmethod
    @abstractmethod
    def install() -> None: ...

    @staticmethod
    @abstractmethod
    def upgrade() -> None: ...

    @override
    def __str__(self) -> str:
        return self.__name__
