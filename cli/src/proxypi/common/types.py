from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Annotated, ParamSpec, TypeVar, final

from pydantic import BaseModel, Field
from typer import Abort

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
    @final
    def __init__(self, name: str) -> None:
        self.name: str = name

    @staticmethod
    @abstractmethod
    def _is_installed() -> bool: ...

    @staticmethod
    @abstractmethod
    def _is_meeting_min_version_required(min_version: tuple[int, ...]) -> bool: ...

    @final
    def is_satisfied(self, min_version: tuple[int, ...]) -> bool:
        return self._is_installed() and self._is_meeting_min_version_required(
            min_version
        )

    @staticmethod
    @abstractmethod
    def install() -> None: ...

    @staticmethod
    @abstractmethod
    def _upgrade() -> None: ...

    @final
    def upgrade(self) -> None:
        if not self._is_installed():
            raise Abort(f"you first need to install package {self.name}")
        self._upgrade()
