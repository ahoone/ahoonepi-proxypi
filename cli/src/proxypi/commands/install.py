from collections.abc import Callable
from typing import Annotated, Literal

from typer import Argument, Context, Typer

from proxypi.commands.dependencies.system_lib import system_lib
from proxypi.commands.dependencies.uv import uv
from proxypi.common.types import Dependency

app = Typer()

DEPENDENCIES: list[Dependency] = [
    uv,
    system_lib,
]


def _autocompletion(ctx: Context, incomplete: str) -> list[str]:
    selected: list[str] = ctx.params.get("dependencies") or []

    matches = [
        dependency
        for dependency in [d.name for d in DEPENDENCIES]
        if dependency.startswith(incomplete)
        and dependency not in selected
        and "all" not in selected
    ]
    if selected == []:
        matches.append("all")

    return matches


@app.command(context_settings={})
def manage_dependencies(
    mode: Annotated[Literal["install", "upgrade"], Argument()],
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
):
    if dependencies == ["all"]:
        dependencies = [d.name for d in DEPENDENCIES]

    for dependency in dependencies:
        func: Callable[[], bool | None] = getattr(globals()[dependency], mode)
        _ = func()
