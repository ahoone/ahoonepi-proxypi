from collections.abc import Callable
from typing import Annotated, Literal

from typer import Argument, Context, Option, Typer

from proxypi.commands.dependencies.uv import uv
from proxypi.common.types import Dependency

app = Typer()

DEPENDENCIES: list[Dependency] = [
    uv,
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
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
    mode: Annotated[Literal["install", "upgrade"], Option("--mode", "-m")],
):
    for dependency in dependencies:
        func: Callable[[], bool | None] = getattr(globals()[dependency], mode)
        _ = func()
