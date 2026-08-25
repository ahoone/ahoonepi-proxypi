import asyncio
import sys
from datetime import datetime, timedelta, timezone
from shlex import quote
from typing import Literal, TextIO

from pydantic import FilePath

from proxypi.common.types import Port
from proxypi.config import config


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


async def __read_stream(
    stream: asyncio.StreamReader,
    output: TextIO,
    chunks: list[bytes],
) -> None:
    while chunk := await stream.read(4096):
        chunks.append(chunk)
        output.buffer.write(chunk)
        output.buffer.flush()


ExecuteCommandMode = Literal["hold", "flush_duplicate", "flush_main"]


async def execute_command(
    port: Port | None,
    bash_command: str,
    timeout: float,
    mode: ExecuteCommandMode = "hold",
    lighthouse_private_key_path: FilePath = config.lighthouse_private_key_path,
    tcp_connection_timeout: int = config.tcp_connection_timeout,
    proxypi_user: str = config.proxypi_user,
) -> tuple[str, timedelta]:
    """
    Summary.

    Args:
        port (Port | None): If None, runs on the host.
        bash_command (str): To give as ready to use, the function encapsulates in `bash -lc '...'`.
        timeout (float): Description.
        mode (ExecuteCommandMode): Description, optional (default: "hold").
        lighthouse_private_key_path (FilePath): Description, optional (default: config.lighthouse_private_key_path).
        tcp_connection_timeout (int): Description, optional (default: config.tcp_connection_timeout).
        proxypi_user (str): Description, optional (default: config.proxypi_user).

    Returns:
        tuple[str, timedelta]: Description.

    Raises:
        ValueError: Description.
        KeyError: Description.
        RuntimeError: Description.
        TimeoutError: Description.
    """

    if mode in ["hold", "flush_duplicate"]:
        stdout = asyncio.subprocess.PIPE
        stderr = asyncio.subprocess.PIPE
    elif mode == "flush_main":
        stdout = None
        stderr = None
    else:
        raise ValueError(f"invalid mode: {mode!r}")

    bash_command = f"bash -lc {quote(bash_command)}"

    if port is not None:
        if port not in listen():
            raise KeyError(f"given {port} is not currently in use") from None
        conn = [
            "ssh",
            "-tt",
            "-i",
            str(lighthouse_private_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"ConnectTimeout={tcp_connection_timeout}",
            "-p",
            str(port),
            f"{proxypi_user}@localhost",
        ]
        proc = await asyncio.create_subprocess_exec(
            *conn,
            bash_command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
    else:
        proc = await asyncio.create_subprocess_shell(
            bash_command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )

    command_stdout: str | bytes
    command_stderr: str | bytes

    start_beacon = datetime.now(timezone.utc)
    end_beacon: datetime

    try:
        if mode == "hold":
            command_stdout, command_stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            end_beacon = datetime.now(timezone.utc)

            command_stdout = command_stdout.decode()
            command_stderr = command_stderr.decode()

        if mode == "flush_duplicate":
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []
            await asyncio.wait_for(
                asyncio.gather(
                    __read_stream(proc.stdout, sys.stdout, stdout_chunks),
                    __read_stream(proc.stderr, sys.stderr, stderr_chunks),
                    proc.wait(),
                ),
                timeout=timeout,
            )

            end_beacon = datetime.now(timezone.utc)

            command_stdout = b"".join(stdout_chunks).decode()
            command_stderr = b"".join(stderr_chunks).decode()
        elif mode == "flush_main":
            await asyncio.wait_for(
                proc.wait(),
                timeout=timeout,
            )

            end_beacon = datetime.now(timezone.utc)

            command_stdout = ""
            command_stderr = ""

        if proc.returncode != 0:
            raise RuntimeError(
                f"`{bash_command}` failed with "
                + f"`{proc.returncode}` on host: "
                + f"{command_stderr.strip()}"
            )

        return (
            command_stdout,
            end_beacon - start_beacon,
        )

    except asyncio.TimeoutError:
        proc.terminate()
        await proc.wait()
        raise TimeoutError(
            f"`{bash_command}` timed out after {timeout}s on host`"
        ) from None

    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()
