import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar

from pydantic import BaseModel, create_model
from typer import Argument, Context, Option

from proxypi.common.config import config
from proxypi.common.options import NodeIDOption
from proxypi.common.types import (
    Dependency,
    DependencyMode,
    DependencyModeResponse,
    NodeID,
    Port,
    node_id_to_port,
)
from proxypi.common.utils import print_table, to_table
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


async def run_dependencies_mode_on_target(
    sem: asyncio.Semaphore,
    mode: DependencyMode,
    dependencies: list[str],
    target: Port | None,
) -> list[DependencyModeResponse]:
    responses: list[DependencyModeResponse] = []
    async with sem:
        for dependency in dependencies:
            coro: Callable[[Port | None], Awaitable[DependencyModeResponse]] = getattr(
                globals()[dependency], mode
            )
            responses.append(await coro(target))
    return responses


def get_dynamic_model(dependencies: list[str]) -> type[BaseModel]:
    dynamic_columns: dict[str, tuple[type, object]] = {"node_id": (int, ...)}
    for dependency in dependencies:
        dynamic_columns[dependency] = (str, ...)

    return create_model(
        "DynamicModel",
        **dynamic_columns,
    )


def format_to_dynamic_model(
    dynamic_model: type[BaseModel], response: list[DependencyModeResponse]
) -> BaseModel:
    node_id = response[0].target
    entries = dict(
        {"node_id": node_id},
        **{d.dependency: str(d) for d in response},
    )
    return dynamic_model(**entries)


async def run_on_targets(
    dynamic_model: type[BaseModel],
    mode: DependencyMode,
    dependencies: list[str],
    targets: list[NodeID],
    *,
    concurrent_conn=config.concurrent_conn,
) -> list[BaseModel]:
    rows = []
    sem = asyncio.Semaphore(concurrent_conn)
    for target in targets:
        port = node_id_to_port(target) if target != 1 else None
        response = await run_dependencies_mode_on_target(sem, mode, dependencies, port)
        rows.append(format_to_dynamic_model(dynamic_model, response))
    return rows


def deps(
    mode: Annotated[DependencyMode, Argument()],
    dependencies: Annotated[list[str], Argument(autocompletion=_autocompletion)],
    # all_proxies: Annotated[
    #     bool,
    #     Option(
    #         help="If set to `True`, will ignore the node_id and run on all the proxies."
    #     ),
    # ] = False,
    node_id: NodeIDOption = 1,
):
    """
    Installs or upgrades dependencies on local machine.
    `system_lib` dependency refers to the OS librairies, and includes, other dependencies like WireGuard.
    """
    targets = [node_id]

    if dependencies == ["all"]:
        dependencies = [d.name for d in DEPENDENCIES]

    dynamic_model = get_dynamic_model(dependencies)

    rows = asyncio.run(run_on_targets(dynamic_model, mode, dependencies, targets))
    table = to_table(rows)
    print_table(table)
