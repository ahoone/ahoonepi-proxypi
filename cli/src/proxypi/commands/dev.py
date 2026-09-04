import subprocess
from typing import Literal

from typer import Typer

from proxypi.commands.dependencies.uv import uv
from proxypi.common.config import PROJECT_ROOT

app = Typer()


@app.command(name="venv")
def create_dev_venv():
    """
    Creates virtual environments for each component
    (broker, scraper, common, CLI) for development.
    Intended to be launch on the IDE's host
    while the project is on a remote SSH server.
    """
    if not uv.is_satisfied:
        raise ImportError("uv is not verifying conditions")

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
                "common",
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

    create_venv_from_requirements("broker")
    create_venv_from_requirements("scraper")
    create_venv_from_requirements("tests")
    create_venv_from_toml("common")
    create_venv_from_toml("cli")
