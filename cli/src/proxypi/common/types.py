from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Annotated, Literal, ParamSpec, TypeVar, final, override

from pydantic import BaseModel, Field
from typer import Abort

from proxypi.common.config import config
from proxypi.common.constants import RANGE_PORTS

P = ParamSpec("P")
T = TypeVar("T")

AsyncFunc = Callable[P, Awaitable[T]]

DataModel = TypeVar("DataModel", bound=BaseModel)

# pydantic flavored, not compatible with typer
# NodeID = lighthouse + ProxyID
# ie a ProxyID included in NodeID
Port = Annotated[int, Field(ge=RANGE_PORTS[0], le=RANGE_PORTS[1])]
NodeID = Annotated[int, Field(ge=1, le=config.network_size - 1)]
ProxyID = Annotated[int, Field(ge=2, le=config.network_size - 1)]


def port_to_node_id(
    port: Port, ssh_network_base: int = config.ssh_network_base
) -> NodeID:
    return port - ssh_network_base + 2


def node_id_to_port(
    node_id: NodeID, ssh_network_base: int = config.ssh_network_base
) -> Port:
    return node_id + ssh_network_base - 2


@dataclass
class ExitCodeError(Exception):
    """
    Very similar to subproccess.CalledProcessError
    Considering using it here
    """

    bash_command: str
    host: IPv4Address | Port | None
    returncode: int
    stderr: str

    @override
    def __str__(self) -> str:
        return (
            f"Command `{self.bash_command}` failed on"
            + (f" {self.host}" if self.host else " localhost")
            + f" with exit code {self.returncode}"
            + (f":\n{self.stderr}" if self.stderr != "" else " (stderr is empty).")
        )


class Dependency(ABC):
    @final
    def __init__(
        self,
        name: str,
        *,
        min_version: tuple[int, ...] = (),
    ) -> None:
        self.name: str = name
        self.min_version: tuple[int, ...] = min_version

    @staticmethod
    @abstractmethod
    async def _is_installed(target: Port | None) -> bool: ...

    @abstractmethod
    async def _is_meeting_min_version_required(self, target: Port | None) -> bool: ...

    @final
    async def is_satisfied(self, target: Port | None) -> bool:
        return await self._is_installed(
            target
        ) and await self._is_meeting_min_version_required(target)

    @staticmethod
    @abstractmethod
    async def install(target: Port | None) -> bool: ...

    @staticmethod
    @abstractmethod
    async def _upgrade(target: Port | None) -> bool: ...

    @final
    async def upgrade(self, target: Port | None) -> bool:
        if not await self._is_installed(target):
            raise Abort(f"you first need to install package {self.name}")
        return await self._upgrade(target)

    # @abstractmethod
    # def status(self) -> Literal["up-to-date", ""]
