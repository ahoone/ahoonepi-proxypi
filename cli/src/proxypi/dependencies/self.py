from typing import override

from proxypi.common.types import Dependency, Port


class Self(Dependency):
    @staticmethod
    @override
    async def _is_installed(target: Port | None) -> bool:
        return True

    @override
    async def _is_meeting_min_version_required(self, target: Port | None) -> bool:
        return True

    @staticmethod
    @override
    async def _install(target: Port | None) -> bool:
        return True

    @staticmethod
    @override
    async def _upgrade(target: Port | None) -> bool:
        return True


self = Self("self")
