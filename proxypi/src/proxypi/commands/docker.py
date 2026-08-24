import asyncio
from datetime import timedelta
from pathlib import Path
from shlex import quote

import typer

from proxypi.common.core import execute_command, listen
from proxypi.common.types import Port, SSHPingResponse
from proxypi.common.utils import print_table, to_table
from proxypi.Config import PROJECT_ROOT

app = typer.Typer()

TIMEOUT_BUILD_SCRAPER = 120  # seconds


async def restart_scraper_service(
    port: Port | None = None,
) -> tuple[bool, timedelta | None]:
    instructions = [
        f"cd {quote(str(PROJECT_ROOT))} &&",
        "export USER_UID=$(id -u) &&",
        "export USER_GID=$(id -g) &&",
        "docker compose -f scraper/docker-compose.yml down &&",
        "docker compose -f scraper/docker-compose.yml --env-file .env --env-file config.env up --build -d",
    ]

    try:
        _, timedelta_exec = await execute_command(
            None, instructions, TIMEOUT_BUILD_SCRAPER, mode="flush_duplicate"
        )
        return (True, timedelta_exec)
    except RuntimeError:
        return (False, None)
    except TimeoutError:
        return (False, timedelta(seconds=TIMEOUT_BUILD_SCRAPER))


@app.command()
def test_restart_host_scraper():
    print(asyncio.run(restart_scraper_service()))
