from collections.abc import Callable
from typing import Annotated, Literal

from typer import Argument, Context, Option

from proxypi.common.options import NodeIDOption
from proxypi.common.types import Dependency, node_id_to_port
from proxypi.dependencies.self import self
from proxypi.dependencies.system_lib import system_lib
from proxypi.dependencies.uv import uv

DEPENDENCIES: list[Dependency] = [
    system_lib,
    uv,
    self,
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
    mode: Annotated[Literal["install", "upgrade", "status"], Argument()],
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
    all_proxies: Annotated[
        bool,
        Option(
            help="If set to `True`, will ignore the node_id and run on all the proxies."
        ),
    ] = False,
    node_id: NodeIDOption = 1,
):
    """
    Installs or upgrades dependencies on local machine.
    `system_lib` dependency refers to the OS librairies, and includes, other dependencies like WireGuard.
    """
    target = None if node_id == 1 else node_id_to_port(node_id)

    # async def inner():

    if target is None:
        if dependencies == ["all"]:
            dependencies = [d.name for d in DEPENDENCIES]

        for dependency in dependencies:
            func: Callable[[], bool | None] = getattr(globals()[dependency], mode)
            _ = func()

    else:
        raise NotImplementedError
