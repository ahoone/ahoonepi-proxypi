import asyncio
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel
from typer import BadParameter

from proxypi.common.config import PROJECT_ROOT, config
from proxypi.common.core import ExecuteCommandMode, execute_command, listen_ports
from proxypi.common.options import NodeIDOption
from proxypi.common.types import Port, node_id_to_port
from proxypi.common.utils import (
    gather_with_progress,
    gather_with_semaphore,
    print_table,
    run_with_spinner,
    to_table,
)

TIMEOUT_RESTART = 300  # seconds
TIMEOUT_STOP = 30  # seconds

Action = Literal["stop", "restart"]


class ServiceResponse(BaseModel):
    port: Port | None
    returncode: Literal["success", "failed", "skipped", "timeout"]
    duration: timedelta | None


async def run_docker_instructions_one_target(
    action: Action,
    timeout: int,
    port: Port | None = None,
    scraper: bool = False,
    broker: bool = False,
    mode: ExecuteCommandMode = "hold",
) -> ServiceResponse:
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

    bash_command = " && ".join(instructions)

    try:
        command_response = await execute_command(
            bash_command, target=port, timeout=timeout, mode=mode
        )
        response = command_response.stdout
        duration = command_response.duration
        if "ERROR: NODE_ROLE must be" in response:
            return ServiceResponse(port=port, returncode="skipped", duration=duration)

        return ServiceResponse(port=port, returncode="success", duration=duration)
    except RuntimeError:
        return ServiceResponse(port=port, returncode="failed", duration=None)
    except TimeoutError:
        return ServiceResponse(
            port=port,
            returncode="timeout",
            duration=timedelta(seconds=timeout),
        )


# @(run_with_spinner("Reloading..."))
async def restart_services_on_all(
    action: Action,
    timeout: int,
    scraper: bool = False,
    broker: bool = False,
    concurrent_conn: int = config.concurrent_conn,
) -> list[ServiceResponse]:

    tasks = [
        run_docker_instructions_one_target(
            action=action,
            port=port,
            scraper=scraper,
            broker=broker,
            timeout=timeout,
            mode="hold",
        )
        for port in [None, *listen_ports()]
    ]
    return await gather_with_progress(*tasks, concurrent_conn=concurrent_conn)
    # return await gather_with_semaphore(*tasks, concurrent_conn=concurrent_conn)
    # return await asyncio.gather(*tasks)


def deploy(
    action: Literal["stop", "restart"] = "restart",
    a: bool = False,
    node_id: NodeIDOption = 1,
    scraper: bool = False,
    broker: bool = False,
    timeout: int | None = None,
):
    """
    Manages the fleet's services with a common input.
    """
    port: Port | None = None if node_id == 1 else node_id_to_port(node_id)

    if timeout is None:
        if action == "stop":
            timeout = TIMEOUT_STOP
        elif action == "restart":
            timeout = TIMEOUT_RESTART

    if a and port:
        raise BadParameter("if you want to restart on all Pis, do not provide a port")

    if not (scraper or broker):
        raise BadParameter("you must provide at least one service to restart")

    if a:
        rows: list[ServiceResponse] = asyncio.run(
            restart_services_on_all(
                action=action,
                timeout=timeout,
                scraper=scraper,
                broker=broker,
            ),
        )
        table = to_table(rows)
        print_table(table)
    else:
        _ = asyncio.run(
            run_docker_instructions_one_target(
                action=action,
                timeout=timeout,
                port=port,
                scraper=scraper,
                broker=broker,
                mode="flush_main",
            )
        )
