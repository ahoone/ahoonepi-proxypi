import shutil
import subprocess
from typing import override

import requests

from proxypi.common.types import Dependency

INSTALL_URL: str = "https://astral.sh/uv/install.sh"
MIN_VERSION: tuple[int, ...] = (0, 12, 7)  # The one with which this was written


class UV(Dependency):
    @staticmethod
    @override
    def _is_installed() -> bool:
        return shutil.which("uv") is not None

    @override
    def _is_meeting_min_version_required(self) -> bool:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )

        installed_version = result.stdout.split()[1]

        installed = tuple(int(x) for x in installed_version.split("."))

        return installed >= self.min_version

    @staticmethod
    @override
    def install(url: str = INSTALL_URL) -> None:
        response = requests.get(url)
        response.raise_for_status()
        installer = response.content

        _ = subprocess.run(
            ["sh"],
            input=installer,
            check=True,
        )

    @staticmethod
    @override
    def _upgrade() -> None:
        _ = subprocess.run(
            ["uv", "self", "update"],
            check=True,
        )


uv = UV("uv", min_version=MIN_VERSION)
