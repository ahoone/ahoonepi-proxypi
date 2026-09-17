from typing import override

from proxypi.common.core import execute_command
from proxypi.common.Dependency import Dependency
from proxypi.common.types import ExitCodeError, Port


def extract_wireguard_version(raw: str) -> tuple[int, ...]:
    # wireguard-tools v1.0.20250521 - https://git.zx2c4.com/wireguard-tools/
    version_string = raw.split(" ")[1]
    version_string = version_string[1:]
    return tuple(int(x) for x in version_string.split("."))


class WireGuardTools(Dependency):
    @staticmethod
    @override
    async def _is_installed(target: Port | None) -> bool:
        response = await execute_command(
            "which wg",
            target=target,
            capture_stdout=False,
            raise_exit_code=False,
        )

        return response.returncode == 0

    @staticmethod
    @override
    async def _get_installed_version(target: Port | None) -> tuple[int, ...]:
        response = await execute_command(
            "wg --version",
            target=target,
            capture_stdout=True,
            raise_exit_code=False,
        )

        return extract_wireguard_version(response.stdout)

    @override
    async def _install(self, target: Port | None) -> bool:
        try:
            await self._apt_update(target)

            response = await execute_command(
                "sudo apt-get install wireguard-tools",
                target=target,
                capture_stdout=True,
                raise_exit_code=True,
            )

            return response.stdout == ""
        except ExitCodeError:
            return False

    @override
    async def _upgrade(self, target: Port | None) -> bool:
        try:
            await self._apt_update(target)

            _ = await execute_command(
                "sudo apt-get install --only-upgrade wireguard-tools",
                target=target,
                raise_exit_code=True,
            )
            return True
        except ExitCodeError:
            return False


wireguard_tools = WireGuardTools("wireguard_tools")
