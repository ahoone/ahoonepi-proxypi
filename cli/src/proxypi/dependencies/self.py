from typing import override

from proxypi.common.config import PROJECT_ROOT
from proxypi.common.types import Dependency


class Self(Dependency):
    @staticmethod
    @override
    def _is_installed() -> bool:
        return True

    @override
    def _is_meeting_min_version_required(self) -> bool:
        return True

    @staticmethod
    @override
    def install() -> None:
        pass

    @staticmethod
    @override
    def _upgrade() -> None:

        with open(PROJECT_ROOT / ".git" / "config") as f:
            lines = f.readlines()

        print(lines)


self = Self("self")
