from typing import override

import httpx

from proxypi.common.core import execute_command
from proxypi.common.Dependency import Dependency
from proxypi.common.types import ExitCodeError, Port

INSTALL_URL: str = "https://releases.astral.sh/installers/uv/latest/uv-installer.sh"
MIN_VERSION: tuple[int, ...] = (0, 12, 7)  # The version with which this was written


class UV(Dependency):
    @staticmethod
    @override
    async def _is_installed(target: Port | None) -> bool:
        try:
            response = await execute_command(
                "uv",
                target=target,
                capture_stdout=True,
                raise_exit_code=True,
            )

            return response.stdout == ""
        except ExitCodeError:
            return False

    @staticmethod
    @override
    async def _get_installed_version(target: Port | None) -> tuple[int, ...]:
        response = await execute_command(
            "uv --version", target=target, capture_stdout=True, raise_exit_code=True
        )
        return tuple(int(x) for x in response.stdout.split()[1].split("."))

    @override
    async def _install(self, target: Port | None, *, url: str = INSTALL_URL) -> bool:
        """
        it creates one client per request, that's bad. Should have one for the entire CLI
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            _ = response.raise_for_status()
            installer = response.text
            _ = await execute_command(
                installer, target=target, raise_exit_code=True, force_tty_remote=False
            )
            return True
        except httpx.ConnectError:
            return False
        except httpx.HTTPStatusError:
            return False
        except ExitCodeError:
            return False

    @override
    async def _upgrade(self, target: Port | None) -> bool:
        try:
            _ = await execute_command(
                "uv self update",
                target=target,
                timeout=60,
                raise_exit_code=True,
                force_tty_remote=False,
            )
            return True
        except ExitCodeError:
            return False
        except TimeoutError:
            return False


uv = UV("uv", min_version=MIN_VERSION)
