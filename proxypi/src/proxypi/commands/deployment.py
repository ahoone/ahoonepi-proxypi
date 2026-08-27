import asyncio
import subprocess
from datetime import timedelta
from shlex import quote
from typing import Literal

import typer
from proxypi.common.core import ExecuteCommandMode, execute_command, listen
from proxypi.common.options import PortOption
from proxypi.common.types import Port
from proxypi.common.utils import print_table, run_with_spinner, to_table
from proxypi.config import config
from pydantic import BaseModel

app = typer.Typer()

TIMEOUT_RESTART = 200  # seconds
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
        f"cd /home/{config.proxypi_user}/{config.git_repository}",
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
        response, duration = await execute_command(
            bash_command, port=port, timeout=timeout, mode=mode
        )
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


@run_with_spinner("Restarting services...")
async def restart_services_on_all(
    action: Action,
    timeout: int,
    scraper: bool = False,
    broker: bool = False,
) -> list[ServiceResponse]:

    return await asyncio.gather(
        *[
            run_docker_instructions_one_target(
                action=action,
                port=port,
                scraper=scraper,
                broker=broker,
                timeout=timeout,
                mode="hold",
            )
            for port in [None, *listen()]
        ]
    )


@app.command()
def run_tests(
    scraper: bool = False,
    broker: bool = False,
    mode: Literal["logs", "flush"] = "flush",
):
    if not (scraper or broker):
        raise typer.BadParameter("you must provide at least one service to restart")

    instructions: list[str] = [
        f"cd /home/{config.proxypi_user}/{config.git_repository}"
    ]

    services: list[str] = []
    if scraper:
        services.append("/app/tests/tests/test_scraper.py")
    if broker:
        services.append("/app/tests/tests/test_broker.py")
    instructions.append(f'export PYTEST_TARGETS="{" ".join(services)}"')

    if mode == "logs":
        instructions.append(
            "docker compose -f tests/docker-compose.yml --env-file .env --env-file config.env up --build -d"
        )
        bash_command = " && ".join(instructions)
        bash_command = f"bash -lc {quote(bash_command)}"
        _ = subprocess.run(
            bash_command,
            shell=True,
            check=True,
        )
    elif mode == "flush":
        raise NotImplementedError


@app.command()
def restart_services(
    action: Literal["stop", "restart"] = "restart",
    a: bool = False,
    port: PortOption = None,
    scraper: bool = False,
    broker: bool = False,
    timeout: int | None = None,
):
    if timeout is None:
        if action == "stop":
            timeout = TIMEOUT_STOP
        elif action == "restart":
            timeout = TIMEOUT_RESTART

    if a and port:
        raise typer.BadParameter(
            "if you want to restart on all Pis, do not provide a port"
        )

    if not (scraper or broker):
        raise typer.BadParameter("you must provide at least one service to restart")

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
