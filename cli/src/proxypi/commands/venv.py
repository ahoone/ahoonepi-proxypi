import subprocess
from typing import Literal

from proxypi.commands.dependencies.uv import uv
from proxypi.common.config import PROJECT_ROOT


def create_venv_from_requirements(
    subdirectory: Literal["broker", "scraper", "tests"],
):
    _ = subprocess.run(
        [
            "uv",
            "venv",
            "--no-project",
            "--clear",
            "--python",
            "3.10",
            f"{PROJECT_ROOT}/{subdirectory}/.venv",
        ],
        check=True,
    )

    _ = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--link-mode",
            "copy",
            "--python",
            f"{PROJECT_ROOT}/{subdirectory}/.venv/bin/python",
            "-r",
            f"{PROJECT_ROOT}/{subdirectory}/requirements.txt",
            "-e",
            f"{PROJECT_ROOT}/common",
        ],
        check=True,
    )


def create_venv_from_toml(subdirectory: Literal["common", "cli"]):

    _ = subprocess.run(
        [
            "uv",
            "sync",
            "--link-mode",
            "copy",
            "--directory",
            f"{PROJECT_ROOT}/{subdirectory}",
        ],
        check=True,
    )


def venv():
    """
    Creates virtual environments for each component (broker, scraper, common, CLI, tests) for development.
    Intended to be launch on the IDE's host while the project is on a remote SSH server (instead of using the remote interpreter option).
    """
    if not uv.is_satisfied:
        raise ImportError("uv is not verifying conditions")

    create_venv_from_requirements("broker")
    create_venv_from_requirements("scraper")
    create_venv_from_requirements("tests")
    create_venv_from_toml("common")
    create_venv_from_toml("cli")
