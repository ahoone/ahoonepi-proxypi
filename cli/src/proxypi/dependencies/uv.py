import shutil
import subprocess
from typing import override

import requests

from proxypi.common.core import execute_command
from proxypi.common.types import Dependency, ExitCodeError

INSTALL_URL: str = "https://astral.sh/uv/install.sh"
MIN_VERSION: tuple[int, ...] = (0, 12, 7)  # The one with which this was written


class UV(Dependency):
    @staticmethod
    @override
    async def _is_installed() -> bool:
        return shutil.which("uv") is not None

    @override
    async def _is_meeting_min_version_required(self) -> bool:
        # response = await
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
    async def install(url: str = INSTALL_URL) -> None:
        response = requests.get(url)
        response.raise_for_status()
        installer = response.content
        response = await execute_command(installer, raise_exit_code=False)

    @staticmethod
    @override
    async def _upgrade() -> bool:
        response = await execute_command("uv self update", raise_exit_code=False)
        return response.returncode


uv = UV("uv", min_version=MIN_VERSION)
