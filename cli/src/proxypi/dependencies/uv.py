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
        response = await execute_command(
            "uv", target=target, mode="hold", raise_exit_code=False
        )

        return response.stdout == ""

    @staticmethod
    @override
    async def _get_installed_version(target: Port | None) -> tuple[int, ...]:
        response = await execute_command(
            "uv --version", target=target, mode="hold", raise_exit_code=True
        )
        return tuple(int(x) for x in response.stdout.split()[1].split("."))

    @staticmethod
    @override
    async def _install(target: Port | None, *, url: str = INSTALL_URL) -> bool:
        """
        it creates one client per request, that's bad. Should have one for the entire CLI
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            _ = response.raise_for_status()
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
        try:
            _ = await execute_command(
                "uv self update", target=target, raise_exit_code=True
            )
            return True
        except ExitCodeError:
            return False


uv = UV("uv", min_version=MIN_VERSION)
