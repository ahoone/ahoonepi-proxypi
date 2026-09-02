import subprocess
from typing import override

from proxypi.common.types import Dependency


class SystemLib(Dependency):
    @staticmethod
    @override
    def _is_installed() -> bool:
        return True

    @staticmethod
    @override
    def _is_meeting_min_version_required(min_version: tuple[int, ...]) -> bool:
        return True

    @staticmethod
    @override
    def install() -> None:
        return

    @staticmethod
    @override
    def _upgrade() -> None:
        _ = subprocess.run(
            ["sudo", "apt-get", "update"],
            check=True,
        )
        _ = subprocess.run(
            ["sudo", "apt-get", "upgrade", "-y"],
            check=True,
        )


system_lib = SystemLib("system_lib")
