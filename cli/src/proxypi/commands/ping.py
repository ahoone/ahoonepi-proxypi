import asyncio
import ipaddress
import re
import subprocess
from datetime import timedelta
from ipaddress import IPv4Address, IPv4Network, IPv6Address
from typing import Literal

import typer
from pydantic import BaseModel

from proxypi.common.config import PROJECT_ROOT, config
from proxypi.common.core import execute_command, listen_ports
from proxypi.common.types import ExitCodeError, Port
from proxypi.common.utils import print_table, run_with_spinner, to_table

app = typer.Typer()

TIMEOUT_PING = 60  # seconds
CONCURRENT_CALLS = 20
PING_SAMPLE_SIZE = 4


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
        sem: asyncio.Semaphore,
    ) -> SSHPingResponse:
        async with sem:
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
                bash_command, target=port, timeout=timeout
            )

            stdout = stdout.strip().split("|")
            start_internet_beacon = timedelta(microseconds=int(stdout[2]))
            end_internet_beacon = timedelta(microseconds=int(stdout[4]))

            return SSHPingResponse(
                hostname=stdout[0],
                node_id=int(stdout[1]),
                port=port,
                ipv6_address=IPv6Address(stdout[3]),
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
            ipv6_address=IPv6Address(stdout[2]),
            timedelta_internet=end_internet_beacon - start_internet_beacon,
        )

    @classmethod
    @run_with_spinner("Pinging...")
    async def ping_all(
        cls, timeout: int, concurrent_calls: int = CONCURRENT_CALLS
    ) -> list[SSHPingResponse]:
        ports = listen_ports()

        sem = asyncio.Semaphore(concurrent_calls)

        rows: list[SSHPingResponse] = await asyncio.gather(
            cls.ping_lighthouse(timeout),
            *[cls.ping_one(port, timeout, sem) for port in ports],
            return_exceptions=False,
        )

        return rows


class VPNPingResponse(BaseModel):
    ipv4_address: IPv4Address
    downside_loss: float
    downside_latency: timedelta | None
    upside_loss: float | None
    upside_latency: timedelta | None


class VPN:
    @staticmethod
    async def ping(
        ipv4_address: IPv4Address,
        downside: bool,
        timeout: int,
        sample_size: int = PING_SAMPLE_SIZE,
        config_wireguard_network: IPv4Network = config.wireguard_network,
    ) -> tuple[float, timedelta | None]:
        """
        Returns a couple (latency, loss).
        If downside set to `True`, from the lighthouse to the proxy,
        else from the proxy to the lighthouse (ie upside).
        """
        if downside:
            bash_command = f"ping -q -c {sample_size} {ipv4_address}"
            target = None
        else:
            bash_command = f"ping -q -c {sample_size} {config_wireguard_network.network_address + 1}"
            target = ipv4_address
        try:
            response, _ = await execute_command(
                bash_command,
                target=target,
                timeout=timeout,
                mode="hold",
                raise_exit_code=True,
            )
        except ExitCodeError:
            return (100.0, None)

        loss: float
        match = re.search(r"([\d.]+)% packet loss", response)
        if match:
            loss = float(match.group(1))
        else:
            raise ValueError(response)

        avg_rtt: timedelta
        match = re.search(r"[\d.]+/[\d.]+/([\d.]+)/[\d.]+ ms", response)
        if match:
            avg_rtt = timedelta(milliseconds=float(match.group(1)))
        else:
            raise ValueError(response)

        return (loss, avg_rtt)

    @staticmethod
    def get_registered_ips(
        config_wireguard_network: IPv4Network = config.wireguard_network,
    ) -> list[IPv4Address]:
        response = subprocess.run(
            ["sudo", "wg", "show", "wg0", "allowed-ips"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        addresses: list[IPv4Address] = []

        for line in response.splitlines():
            _, allowed_ip = line.split("\t", 1)
            allowed_ip = ipaddress.IPv4Network(allowed_ip).network_address
            if (
                allowed_ip in config_wireguard_network
                and allowed_ip != config_wireguard_network.broadcast_address
            ):
                addresses.append(allowed_ip)

        return addresses

    @classmethod
    @run_with_spinner("Pinging...")
    async def ping_all(
        cls, timeout: int, concurrent_calls: int = CONCURRENT_CALLS
    ) -> list[VPNPingResponse]:

        sem = asyncio.Semaphore(concurrent_calls)

        async def ping_and_callback(
            ip: IPv4Address, sem: asyncio.Semaphore
        ) -> VPNPingResponse:
            downside_loss, downside_latency = await cls.ping(ip, True, timeout)

            if downside_latency is None:
                upside_loss, upside_latency = None, None
            else:
                upside_loss, upside_latency = await cls.ping(ip, False, timeout)

            return VPNPingResponse(
                ipv4_address=ip,
                downside_loss=downside_loss,
                downside_latency=downside_latency,
                upside_loss=upside_loss,
                upside_latency=upside_latency,
            )

        return await asyncio.gather(
            *[ping_and_callback(ip, sem) for ip in cls.get_registered_ips()],
            return_exceptions=False,
        )


def ping(mode: Literal["ssh", "vpn"]):
    """
    Tests the nodes' connectivity accordingly to the given method.
    """
    if mode == "ssh":
        coro = SSH.ping_all(TIMEOUT_PING)
    elif mode == "vpn":
        coro = VPN.ping_all(TIMEOUT_PING)

    rows = asyncio.run(coro)
    table = to_table(rows)
    print_table(table)
