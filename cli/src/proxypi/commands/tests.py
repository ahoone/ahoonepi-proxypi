import subprocess
from shlex import quote
from typing import Literal

from typer import BadParameter

from proxypi.common.config import config


def tests(
    scraper: bool = False,
    broker: bool = False,
    mode: Literal["logs", "flush"] = "flush",
):
    """
    Launches the test suite.
    """
    if not (scraper or broker):
        raise BadParameter("you must provide at least one service to restart")

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
