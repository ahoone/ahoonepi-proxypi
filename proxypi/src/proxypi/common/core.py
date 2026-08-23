import asyncio
from datetime import datetime, timedelta, timezone

from pydantic import FilePath

from proxypi.common.types import Port
from proxypi.Config import config


def listen(
    ssh_network_base: Port = config.ssh_network_base,
    network_size: int = config.network_size,
) -> list[Port]:
    """
    Inspects directly the kernel socket table at `/proc/net/tcp`.

    Args:
        ssh_network_base (Port): Description, optional (default: config.ssh_network_base).
        network_size (int): Description, optional (default: config.network_size).

    Returns:
        list[Port]: Description.
    """

    inspection_range: list[Port] = [x + ssh_network_base for x in range(network_size)]

    with open("/proc/net/tcp") as f:
        lines = f.readlines()

    header_row = lines[0].split()
    rows = [dict(zip(header_row, line.split())) for line in lines[1:]]

    found: list[Port] = []
    for row in rows:
        address, port = row["local_address"].split(":")
        address = int(address, 16)
        port = int(port, 16)
        # checks the status is LISTEN (cf `include/net/tcp_states.h`)
        # checks we're on the host
        if int(row["st"], 16) != 10 or address != 0 or port not in inspection_range:
            continue
        found.append(port)

    return found


async def execute_command(
    port: Port,
    command: list[str],
    timeout: float,
    lighthouse_private_key_path: FilePath = config.lighthouse_private_key_path,
    tcp_connection_timeout: int = config.tcp_connection_timeout,
    proxypi_user: str = config.proxypi_user,
) -> tuple[str, timedelta]:
    """
    Executes a command on ONE node.

    Args:
        port (Port): Description.
        command (list[str]): Description.
        timeout (float): Description.
        lighthouse_private_key_path (FilePath): Description, optional (default: config.lighthouse_private_key_path).
        tcp_connection_timeout (int): Description, optional (default: config.tcp_connection_timeout).
        proxypi_user (str): Description, optional (default: config.proxypi_user).

    Returns:
        str: std_out of the subprocess.

    Raises:
        RuntimeError: Description.
    """
    proc: asyncio.subprocess.Process | None = None

    conn = [
        "ssh",
        "-i",
        str(lighthouse_private_key_path),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"ConnectTimeout={tcp_connection_timeout}",
        "-p",
        str(port),
        f"{proxypi_user}@localhost",
        *command,
    ]

    try:
        start_beacon = datetime.now(timezone.utc)
        proc = await asyncio.create_subprocess_exec(
            *conn,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )

        end_beacon = datetime.now(timezone.utc)

        if proc.returncode != 0:
            raise RuntimeError(
                f"`{' '.join(command)}` failed with "
                + f"`{proc.returncode}` at `{port}@localhost`: "
                + f"{stderr.decode().strip()}"
            )

        return (stdout.decode(), end_beacon - start_beacon)

    except asyncio.TimeoutError:
        raise RuntimeError(
            f"`{' '.join(command)}` timed out after {timeout}s at `{port}@localhost`"
        ) from None

    finally:
        if proc and proc.returncode is None:
            proc.terminate()
            await proc.wait()
