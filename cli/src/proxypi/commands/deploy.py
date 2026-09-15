import asyncio
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel
from typer import BadParameter, Context

from proxypi.common.config import PROJECT_ROOT, config
from proxypi.common.core import ExecuteCommandMode, execute_command
from proxypi.common.listen import listen_node_ids
from proxypi.common.options import NodeIDOption
from proxypi.common.stdout import CONSOLE
from proxypi.common.types import NodeID, node_id_to_port
from proxypi.common.utils import gather_with_progress, to_table

TIMEOUT_RESTART = 300  # seconds
TIMEOUT_STOP = 30  # seconds

Action = Literal["stop", "restart"]


class ServiceResponse(BaseModel):
    node_id: NodeID
    returncode: Literal["success", "failed", "skipped", "timeout"]
    duration: timedelta | None


def get_instructions(
    action: Action,
    scraper: bool = False,
    broker: bool = False,
) -> str:

    instructions = [
        f"cd {PROJECT_ROOT}",
        "source .env",
    ]

    if scraper:
        instructions.extend(
            [
                '[[ "${NODE_ROLE:-}" == *"SCRAPER"* ]] || { echo "ERROR: NODE_ROLE must be SCRAPER (got: ${NODE_ROLE:-unset})" >&2; exit 0; }',
                "export USER_UID=$(id -u)",
                "export USER_GID=$(id -g)",
                "docker compose -f scraper/docker-compose.yml down",
            ]
        )
        if action == "restart":
            instructions.append(
                "docker compose -f scraper/docker-compose.yml --env-file .env --env-file config.env up --build -d",
            )

    if broker:
        instructions.extend(
            [
                '[[ "${NODE_ROLE:-}" == *"LIGHTHOUSE"* ]] || { echo "ERROR: NODE_ROLE must be LIGHTHOUSE (got: ${NODE_ROLE:-unset})" >&2; exit 0; }',
                "docker compose -f broker/docker-compose.yml down",
            ]
        )
        if action == "restart":
            instructions.append(
                "docker compose -f broker/docker-compose.yml --env-file .env --env-file config.env up --build -d",
            )

    return " && ".join(instructions)


async def run_docker_instructions_one_target(
    node_id: NodeID,
    action: Action,
    timeout: int,
    mode: ExecuteCommandMode,
    scraper: bool = False,
    broker: bool = False,
) -> ServiceResponse:
    port = None if node_id == 1 else node_id_to_port(node_id)

    bash_command = get_instructions(action, scraper, broker)

    try:
        command_response = await execute_command(
            bash_command,
            target=port,
            timeout=timeout,
            mode=mode,
            capture_stdout=True,
        )
        response = command_response.stdout
        duration = command_response.duration
        if "ERROR: NODE_ROLE must be" in response:
            return ServiceResponse(
                node_id=node_id, returncode="skipped", duration=duration
            )

        return ServiceResponse(node_id=node_id, returncode="success", duration=duration)
    except RuntimeError:
        return ServiceResponse(node_id=node_id, returncode="failed", duration=None)
    except TimeoutError:
        return ServiceResponse(
            node_id=node_id,
            returncode="timeout",
            duration=timedelta(seconds=timeout),
        )


async def restart_services_on_targets(
    targets: list[NodeID],
    action: Action,
    timeout: int,
    mode: ExecuteCommandMode,
    scraper: bool = False,
    broker: bool = False,
    concurrent_conn: int = config.concurrent_conn,
) -> list[ServiceResponse]:

    return await gather_with_progress(
        *[
            run_docker_instructions_one_target(
                node_id=node_id,
                action=action,
                timeout=timeout,
                mode=mode,
                scraper=scraper,
                broker=broker,
            )
            for node_id in targets
        ],
        concurrent_conn=concurrent_conn,
    )


def deploy(
    ctx: Context,
    action: Literal["stop", "restart"] = "restart",
    all_nodes: bool = False,
    node_id: NodeIDOption = 1,
    scraper: bool = False,
    broker: bool = False,
    timeout: int | None = None,
):
    """
    Manages the fleet's services with a common input.
    """

    if all_nodes and node_id:
        raise BadParameter(
            "if you want to restart on all Pis, do not provide a node_id"
        )

    if not (scraper or broker):
        raise BadParameter("you must provide at least one service to restart")

    targets = listen_node_ids() if all_nodes else [node_id]
    if timeout is None:
        timeout = TIMEOUT_STOP if action == "stop" else TIMEOUT_RESTART
    mode = ctx.obj["mode"]

    rows: list[ServiceResponse] = asyncio.run(
        restart_services_on_targets(
            targets=targets,
            action=action,
            timeout=timeout,
            mode=mode,
            scraper=scraper,
            broker=broker,
        ),
    )

    table = to_table(rows)
    CONSOLE.print(table)
