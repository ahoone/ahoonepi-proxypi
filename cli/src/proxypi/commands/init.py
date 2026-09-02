import subprocess
from collections.abc import Callable
from typing import Annotated, Literal

from typer import Argument, Context, Typer

from proxypi.commands.dependencies.system_lib import system_lib
from proxypi.commands.dependencies.uv import uv
from proxypi.common.config import PROJECT_ROOT
from proxypi.common.types import Dependency

app = Typer()

DEPENDENCIES: list[Dependency] = [
    system_lib,
    uv,
]


def _autocompletion(ctx: Context, incomplete: str) -> list[str]:
    selected: list[str] = ctx.params.get("dependencies") or []

    matches: list[str] = []
    if selected == ["all"]:
        return []
    elif selected == []:
        matches.append("all")
    matches.extend(
        [
            dependency
            for dependency in [d.name for d in DEPENDENCIES]
            if dependency.startswith(incomplete) and dependency not in selected
        ]
    )

    return matches


@app.command(name="deps")
def manage_dependencies(
    mode: Annotated[Literal["install", "upgrade"], Argument()],
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
):
    """
    Install or upgrade dependencies on local machine.
    `system_lib` dependency refers to the OS librairies, and includes,
    other dependencies like WireGuard.
    """
    if dependencies == ["all"]:
        dependencies = [d.name for d in DEPENDENCIES]

    for dependency in dependencies:
        func: Callable[[], bool | None] = getattr(globals()[dependency], mode)
        _ = func()


@app.command(name="venv")
def create_dev_venv():
    """
    Creates virtual environments for each component
    (broker, scraper, common, CLI) for development.
    """
    if not uv.is_satisfied:
        raise ImportError("uv is not verifying conditions")

    def create_broker_venv():
        _ = subprocess.run(
            [
                "uv",
                "venv",
                "--no-project",
                "--clear",
                "--python",
                "3.10",
                "broker/.venv",
            ],
            check=True,
        )

        _ = subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                "broker/.venv/bin/python",
                "-r",
                "broker/requirements.txt",
                "-e",
                "common",
            ],
            check=True,
        )

    def create_scraper_venv():
        _ = subprocess.run(
            [
                "uv",
                "venv",
                "--no-project",
                "--clear",
                "--python",
                "3.10",
                "scraper/.venv",
            ],
            check=True,
        )

        _ = subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                "scraper/.venv/bin/python",
                "-r",
                "scraper/requirements.txt",
                "-e",
                "common",
            ],
            check=True,
        )

    create_broker_venv()
    create_scraper_venv()
