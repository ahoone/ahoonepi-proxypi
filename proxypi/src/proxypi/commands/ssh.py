import asyncio
from datetime import timedelta

import typer

from proxypi.common.core import (
    execute_command,
    listen,
)
from proxypi.common.types import Port, SSHPingResponse
from proxypi.common.utils import print_table, run_with_spinner, to_table
from proxypi.config import PROJECT_ROOT

app = typer.Typer()

TIMEOUT_PING = 60  # seconds


async def ping_one(port: Port) -> SSHPingResponse:
    instructions = [
        "printf",
        "'%s|%s|%s|%s|%s'",
        "$(hostname)",
        f"$(. {PROJECT_ROOT}/.env && echo $PROXY_ID)",
        "$(date +%s%6N)",
        "$(curl ifconfig.me 2>/dev/null || echo 'N/A')",
        "$(date +%s%6N)",
    ]

    bash_command = " ".join(instructions)

    stdout, timedelta_exec = await execute_command(port, bash_command, TIMEOUT_PING)

    stdout = stdout.strip().split("|")
    start_internet_beacon = timedelta(microseconds=int(stdout[2]))
    end_internet_beacon = timedelta(microseconds=int(stdout[4]))

    return SSHPingResponse(
        hostname=stdout[0],
        node_id=stdout[1],
        port=port,
        ipv6_address=stdout[3],
        timedelta_ssh_rtt=timedelta_exec - start_internet_beacon + end_internet_beacon,
        timedelta_internet=end_internet_beacon - start_internet_beacon,
    )


async def ping_lighthouse() -> SSHPingResponse:
    instructions = [
        "printf",
        "'%s|%s|%s|%s'",
        "$(hostname)",
        "$(date +%s%6N)",
        "$(curl ifconfig.me 2>/dev/null || echo 'N/A')",
        "$(date +%s%6N)",
    ]

    bash_command = " ".join(instructions)

    stdout, _ = await execute_command(None, bash_command, TIMEOUT_PING)

    stdout = stdout.strip().split("|")
    start_internet_beacon = timedelta(microseconds=int(stdout[1]))
    end_internet_beacon = timedelta(microseconds=int(stdout[3]))

    return SSHPingResponse(
        hostname=stdout[0],
        ipv6_address=stdout[2],
        timedelta_internet=end_internet_beacon - start_internet_beacon,
    )


async def ping_all() -> list[SSHPingResponse]:
    ports = listen()

    rows: list[SSHPingResponse] = await asyncio.gather(
        ping_lighthouse(),
        *[ping_one(port) for port in ports],
        return_exceptions=False,
    )

    return rows


@app.command()
def ping():
    rows = asyncio.run(run_with_spinner(ping_all(), "Pinging...", TIMEOUT_PING))
    table = to_table(rows)
    print_table(table)
