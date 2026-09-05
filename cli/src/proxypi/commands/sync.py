import asyncio
import subprocess
from ipaddress import IPv4Address

from rich import print as rprint

from proxypi.common.config import config
from proxypi.common.core import execute_command, listen_ports
from proxypi.common.types import Port, port_to_proxyid
from proxypi.common.utils import run_with_spinner


async def retrieve_proxy_public_key(
    port: Port, sem: asyncio.Semaphore
) -> tuple[str, Port]:

    async with sem:
        public_key, _ = await execute_command(
            "sudo wg show wg0 public-key",
            target=port,
            timeout=10,
            mode="hold",
        )

    public_key = public_key.strip()

    return (public_key, port)


@run_with_spinner("Retrieving...")
async def retrieve_keys(
    concurrent_conn: int = config.concurrent_conn,
) -> list[tuple[str, Port]]:

    sem = asyncio.Semaphore(concurrent_conn)
    peers = await asyncio.gather(
        *[retrieve_proxy_public_key(port, sem) for port in listen_ports()]
    )

    return peers


def sync():
    """
    Load the proxies' keys in the lighthouse's VPN configuration file.
    """

    peers = asyncio.run(retrieve_keys())

    for public_key, port in peers:
        if not public_key:
            print(f"Proxy on `{port}` was not initialized (no public key).")
            continue

        attributed_address: IPv4Address = config.wireguard_network[
            port_to_proxyid(port)
        ]

        if attributed_address in (
            config.wireguard_network.network_address,
            config.wireguard_network.broadcast_address,
        ):
            raise ValueError("invalid peer address, ie the given proxy id is rotten")

        _ = subprocess.run(
            [
                "sudo",
                "wg",
                "set",
                "wg0",
                "peer",
                public_key,
                "allowed-ips",
                f"{attributed_address}/32",
            ],
            check=True,
        )
        _ = subprocess.run(
            ["sudo", "wg-quick", "save", "wg0"],
            check=True,
            stderr=subprocess.DEVNULL,
        )

    rprint(
        "[bold green]✓ VPN configured successfully![/bold green] "
        "Run [bold cyan]sudo wg show[/bold cyan] to check the connection."
    )
