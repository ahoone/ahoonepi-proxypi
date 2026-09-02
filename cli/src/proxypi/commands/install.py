from typing import Annotated, Callable, Literal

from typer import Argument, Typer

from proxypi.commands.dependencies.uv import uv
from proxypi.common.types import Dependency

app = Typer()

DEPENDENCIES: list[Dependency] = [
    uv,
]


def _autocompletion(
    incomplete: str, dependencies: list[Dependency] = DEPENDENCIES
) -> list[str]:
    return [
        str(dependency)
        for dependency in dependencies
        if str(dependency).startswith(incomplete)
    ]


@app.command()
def manage_dependencies(
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
    mode: Literal["install", "upgrade"],
):
    for dependency in dependencies:
        func: Callable[[], bool | None] = getattr(globals()[dependency], mode)
        print(func())
