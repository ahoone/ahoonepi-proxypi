import asyncio
from datetime import timedelta
from ipaddress import IPv6Address
from typing import Literal

import typer
from pydantic import BaseModel

from proxypi.common.config import PROJECT_ROOT
from proxypi.common.core import execute_command, listen_ports
from proxypi.common.types import Port
from proxypi.common.utils import print_table, run_with_spinner, to_table

app = typer.Typer()

TIMEOUT_PING = 60  # seconds


class SSHPingResponse(BaseModel):
    hostname: str
    node_id: int | None = None
    port: Port | None = None
    ipv6_address: IPv6Address
    timedelta_ssh_rtt: timedelta | None = None
    timedelta_internet: timedelta


class SSH:
    @staticmethod
    async def ping_one(
        port: Port,
        timeout: int,
    ) -> SSHPingResponse:
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

        stdout, timedelta_exec = await execute_command(
            bash_command, port=port, timeout=timeout
        )

        stdout = stdout.strip().split("|")
        start_internet_beacon = timedelta(microseconds=int(stdout[2]))
        end_internet_beacon = timedelta(microseconds=int(stdout[4]))

        return SSHPingResponse(
            hostname=stdout[0],
            node_id=stdout[1],
            port=port,
            ipv6_address=stdout[3],
            timedelta_ssh_rtt=timedelta_exec
            - start_internet_beacon
            + end_internet_beacon,
            timedelta_internet=end_internet_beacon - start_internet_beacon,
        )

    @staticmethod
    async def ping_lighthouse(timeout: int) -> SSHPingResponse:
        instructions = [
            "printf",
            "'%s|%s|%s|%s'",
            "$(hostname)",
            "$(date +%s%6N)",
            "$(curl ifconfig.me 2>/dev/null || echo 'N/A')",
            "$(date +%s%6N)",
        ]

        bash_command = " ".join(instructions)

        stdout, _ = await execute_command(bash_command, timeout=timeout)

        stdout = stdout.strip().split("|")
        start_internet_beacon = timedelta(microseconds=int(stdout[1]))
        end_internet_beacon = timedelta(microseconds=int(stdout[3]))

        return SSHPingResponse(
            hostname=stdout[0],
            ipv6_address=stdout[2],
            timedelta_internet=end_internet_beacon - start_internet_beacon,
        )

    @run_with_spinner("Pinging...")
    async def ping_all(self, timeout: int) -> list[SSHPingResponse]:
        ports = listen_ports()

        rows: list[SSHPingResponse] = await asyncio.gather(
            self.ping_lighthouse(timeout),
            *[self.ping_one(port, timeout) for port in ports],
            return_exceptions=False,
        )

        return rows


def ping(mode: Literal["ssh", "vpn"] = "ssh"):
    """
    Tests the nodes' connectivity accordingly to the given method.
    """
    if mode == "ssh":
        coro = SSH().ping_all(TIMEOUT_PING)
    elif mode == "vpn":
        raise NotImplementedError

    rows = asyncio.run(coro)
    table = to_table(rows)
    print_table(table)
