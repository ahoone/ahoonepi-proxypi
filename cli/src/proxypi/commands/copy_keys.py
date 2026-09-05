import asyncio
from pathlib import Path

from rich import print as rprint

from proxypi.common.config import config
from proxypi.common.core import listen_ports
from proxypi.common.types import Port


async def copy_one_key(
    port: Port,
    sem: asyncio.Semaphore,
    lighthouse_public_key_path: Path = config.lighthouse_public_key_path,
    proxypi_user: str = config.proxypi_user,
) -> None:
    async with sem:
        program_args = [
            "ssh-copy-id",
            "-i",
            str(lighthouse_public_key_path),
            "-p",
            str(port),
            f"{proxypi_user}@localhost",
        ]
        await asyncio.create_subprocess_exec(
            *program_args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )


def copy_keys() -> None:
    """
    Retrieves the remote keys.
    """

    async def inner(concurrent_calls: int = config.concurrent_conn) -> None:
        sem = asyncio.Semaphore(concurrent_calls)
        await asyncio.gather(*[copy_one_key(port, sem) for port in listen_ports()])

    asyncio.run(inner())

    rprint(
        "[bold green]✓ SSH keys copied successfully![/bold green] "
        "Run [bold cyan]proxypi ping ssh[/bold cyan] to check the connection."
    )
