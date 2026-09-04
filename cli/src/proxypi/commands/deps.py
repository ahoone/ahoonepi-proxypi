from collections.abc import Callable
from typing import Annotated, Literal

from typer import Argument, Context

from proxypi.commands.dependencies.system_lib import system_lib
from proxypi.commands.dependencies.uv import uv
from proxypi.common.types import Dependency

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


def deps(
    mode: Annotated[Literal["install", "upgrade"], Argument()],
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
):
    """
    Install or upgrade dependencies on local machine.
    `system_lib` dependency refers to the OS librairies, and includes, other dependencies like WireGuard.
    """
    if dependencies == ["all"]:
        dependencies = [d.name for d in DEPENDENCIES]

    for dependency in dependencies:
        func: Callable[[], bool | None] = getattr(globals()[dependency], mode)
        _ = func()
