from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

PosInt = Annotated[int, Field(ge=1)]

# pydantic flavored, not compatible with typer
# NodeID = lighthouse + ProxyID
# ie a ProxyID included in NodeID
Port = Annotated[int, Field(ge=RANGE_PORTS[0], le=RANGE_PORTS[1])]
NodeID = Annotated[int, Field(ge=1, le=config.network_size - 1)]
ProxyID = Annotated[int, Field(ge=2, le=config.network_size - 1)]


def port_to_node_id(
    port: Port, *, ssh_network_base: int = config.ssh_network_base
) -> NodeID:
    return port - ssh_network_base + 2


def node_id_to_port(
    node_id: NodeID, *, ssh_network_base: int = config.ssh_network_base
) -> Port:
    if NodeID == 1:
        raise ValueError("this action should not be performed on the lighthouse id")
    return node_id + ssh_network_base - 2


class CommandResponse(BaseModel):
    bash_command: str
    target: IPv4Address | Port | None
    returncode: int
    stdout: str
    stderr: str
    duration: timedelta


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


DependencyMode = Literal["install", "upgrade", "status"]


class DependencyModeResponse(BaseModel):
    dependency: str
    mode: DependencyMode
    success: bool
    duration: timedelta
    target: NodeID
    content: str = ""

    @override
    def __str__(self) -> str:
        match self.mode:
            case "install":
                if self.success:
                    return f"installed in {self.duration}"
                else:
                    return "failed"
            case "upgrade":
                return f"upgraded in {self.duration}"
            case "status":
                return f"{self.content}"


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

    @staticmethod
    @abstractmethod
    async def _get_installed_version(target: Port | None) -> tuple[int, ...]: ...

    @final
    async def _is_meeting_min_version_required(self, target: Port | None) -> bool:
        installed_version = await self._get_installed_version(target)
        if len(installed_version) == 0:
            return True
        return installed_version >= self.min_version

    @final
    async def is_satisfied(self, target: Port | None) -> bool:
        return await self._is_installed(
            target
        ) and await self._is_meeting_min_version_required(target)

    @staticmethod
    @abstractmethod
    async def _install(target: Port | None) -> bool: ...

    @final
    async def install(self, target: Port | None) -> DependencyModeResponse:
        started_at = datetime.now(UTC)
        success = await self._install(target)
        duration = datetime.now(UTC) - started_at
        return DependencyModeResponse(
            dependency=self.name,
            mode="install",
            success=success,
            duration=duration,
            target=port_to_node_id(target) if target else 1,
        )

    @staticmethod
    @abstractmethod
    async def _upgrade(target: Port | None) -> bool: ...

    @final
    async def upgrade(self, target: Port | None) -> DependencyModeResponse:
        if not await self._is_installed(target):
            raise Abort(f"you first need to install package {self.name}")

        started_at = datetime.now(UTC)
        success = await self._upgrade(target)
        duration = datetime.now(UTC) - started_at
        return DependencyModeResponse(
            dependency=self.name,
            mode="upgrade",
            success=success,
            duration=duration,
            target=port_to_node_id(target) if target else 1,
        )

    @final
    async def status(self, target: Port | None) -> DependencyModeResponse:
        started_at = datetime.now(UTC)
        try:
            installed_version = await self._get_installed_version(target)
        except ExitCodeError:
            duration = datetime.now(UTC) - started_at
            return DependencyModeResponse(
                dependency=self.name,
                mode="status",
                success=False,
                duration=duration,
                target=port_to_node_id(target) if target else 1,
            )
        duration = datetime.now(UTC) - started_at
        return DependencyModeResponse(
            dependency=self.name,
            mode="status",
            success=True,
            duration=duration,
            target=port_to_node_id(target) if target else 1,
            content=".".join(str(x) for x in installed_version),
        )
