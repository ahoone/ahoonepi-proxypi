from typing import override

from proxypi.common.core import execute_command
from proxypi.common.types import Dependency, ExitCodeError, Port


class SystemLib(Dependency):
    @staticmethod
    @override
    async def _is_installed(target: Port | None) -> bool:
        return True

    @staticmethod
    @override
    async def _get_installed_version(target: Port | None) -> tuple[int, ...]:
        return ()

    @staticmethod
    @override
    async def _install(target: Port | None) -> bool:
        return True

    @staticmethod
    @override
    async def _upgrade(target: Port | None) -> bool:
        try:
            _ = await execute_command(
                "sudo apt-get update", target=target, raise_exit_code=True
            )
            _ = await execute_command(
                "sudo apt-get upgrade -y", target=target, raise_exit_code=True
            )
            _ = await execute_command(
                "sudo apt-get autoremove -y", target=target, raise_exit_code=True
            )
            return True
        except ExitCodeError:
            return False


system_lib = SystemLib("system_lib")
