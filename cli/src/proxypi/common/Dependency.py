from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Literal, final, override

from pydantic import BaseModel
from typer import Abort

from proxypi.common.core import execute_command
from proxypi.common.types import ExitCodeError, NodeID, Port, port_to_node_id

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
    @final
    async def _apt_update(target: Port | None) -> None:
        _ = await execute_command(
            "sudo apt-get update",
            target=target,
            capture_stdout=False,
            raise_exit_code=True,
        )

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

    @abstractmethod
    async def _install(self, target: Port | None) -> bool: ...

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

    @abstractmethod
    async def _upgrade(self, target: Port | None) -> bool: ...

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
