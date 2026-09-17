from typing import override

from proxypi.common.Dependency import Dependency
from proxypi.common.types import Port


class Self(Dependency):
    @staticmethod
    @override
    async def _is_installed(target: Port | None) -> bool:
        return True

    @staticmethod
    @override
    async def _get_installed_version(target: Port | None) -> tuple[int, ...]:
        return ()

    @override
    async def _install(self, target: Port | None) -> bool:
        return True

    @override
    async def _upgrade(self, target: Port | None) -> bool:
        return True


self = Self("self")
