import asyncio
from datetime import timedelta
from typing import Literal

import typer
from pydantic import BaseModel
from rich.progress import track

from proxypi.common.core import ExecuteCommandMode, execute_command, listen
from proxypi.common.typer import PortOption
from proxypi.common.types import Port
from proxypi.common.utils import print_table, run_with_spinner, to_table
from proxypi.config import config

app = typer.Typer()

TIMEOUT_RESTART = 200  # seconds


class RestartServiceResponse(BaseModel):
    port: Port | None
    returncode: Literal["success", "failed", "skipped", "timeout"]
    duration: timedelta | None


async def coroutine_restart_services(
    port: Port | None = None,
    scraper: bool = False,
    broker: bool = False,
    timeout: int = TIMEOUT_RESTART,
    mode: ExecuteCommandMode = "hold",
) -> RestartServiceResponse:
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
                "docker compose -f scraper/docker-compose.yml --env-file .env --env-file config.env up --build -d",
            ]
        )

    if broker:
        instructions.extend(
            [
                '[[ "${NODE_ROLE:-}" == *"LIGHTHOUSE"* ]] || { echo "ERROR: NODE_ROLE must be LIGHTHOUSE (got: ${NODE_ROLE:-unset})" >&2; exit 0; }',
                "docker compose -f broker/docker-compose.yml down",
                "docker compose -f broker/docker-compose.yml --env-file .env --env-file config.env up --build -d",
            ]
        )

    bash_command = " && ".join(instructions)

    try:
        response, duration = await execute_command(
            port, bash_command, timeout, mode=mode
        )
        if "ERROR: NODE_ROLE must be" in response:
            return RestartServiceResponse(
                port=port, returncode="skipped", duration=duration
            )

        return RestartServiceResponse(
            port=port, returncode="success", duration=duration
        )
    except RuntimeError:
        return RestartServiceResponse(port=port, returncode="failed", duration=None)
    except TimeoutError:
        return RestartServiceResponse(
            port=port,
            returncode="timeout",
            duration=timedelta(seconds=timeout),
        )


@run_with_spinner("Restarting services...")
async def restart_services_on_all(
    scraper: bool = False,
    broker: bool = False,
    timeout: int = TIMEOUT_RESTART,
) -> list[RestartServiceResponse]:

    return await asyncio.gather(
        *[
            coroutine_restart_services(
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
def restart_services(
    all: bool = False,
    port: PortOption = None,
    scraper: bool = False,
    broker: bool = False,
    timeout: int = TIMEOUT_RESTART,
):

    if all and port:
        raise ValueError("if you want to restart on all Pis, do not provide a port")

    if not (scraper or broker):
        raise ValueError("you must at least provide one service to restart")

    if all:
        rows: list[RestartServiceResponse] = asyncio.run(
            restart_services_on_all(
                scraper=scraper,
                broker=broker,
                timeout=timeout,
            ),
        )
        table = to_table(rows)
        print_table(table)
    else:
        _ = asyncio.run(
            coroutine_restart_services(
                port=port,
                scraper=scraper,
                broker=broker,
                timeout=timeout,
                mode="flush_main",
            )
        )
