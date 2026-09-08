from typing import override

import httpx

from proxypi.common.core import execute_command
from proxypi.common.types import Dependency, ExitCodeError, Port

INSTALL_URL: str = "https://releases.astral.sh/installers/uv/latest/uv-installer.sh"
MIN_VERSION: tuple[int, ...] = (0, 12, 7)  # The version with which this was written


class UV(Dependency):
    @staticmethod
    @override
    async def _is_installed(target: Port | None) -> bool:
        response = await execute_command("uv", target=target, mode="hold")

        return response.stdout == "-bash: uv: command not found"

    @override
    async def _is_meeting_min_version_required(self, target: Port | None) -> bool:
        response = await execute_command("uv --version", target=target, mode="hold")

        installed_version = response.stdout.split()[1]

        installed = tuple(int(x) for x in installed_version.split("."))

        return installed >= self.min_version

    @staticmethod
    @override
    async def _install(target: Port | None, *, url: str = INSTALL_URL) -> bool:
        """
        it creates one client per request, that's bad. Should have one for the entire CLI
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            response.raise_for_status()
            installer = response.text
            _ = await execute_command(installer, target=target, raise_exit_code=True)
            return True
        except httpx.HTTPStatusError:
            return False
        except ExitCodeError:
            return False

    @staticmethod
    @override
    async def _upgrade(target: Port | None) -> bool:
        response = await execute_command(
            "uv self update", target=target, raise_exit_code=False
        )
        return response.returncode


uv = UV("uv", min_version=MIN_VERSION)
