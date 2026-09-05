import asyncio
import sys
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from shlex import quote
from typing import Literal, TextIO, TypeVar

from pydantic import FilePath

from proxypi.common.config import config
from proxypi.common.types import ExitCodeError, Port, ProxyID

T = TypeVar("T")


def listen_ports(
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


def listen_proxyids() -> list[ProxyID]:
    ports: list[Port] = listen_ports()
    return [port - config.ssh_network_base + 2 for port in ports]


async def __read_stream(
    stream: asyncio.StreamReader,
    output: TextIO,
    chunks: list[bytes],
) -> None:
    while chunk := await stream.read(4096):
        chunks.append(chunk)
        _ = output.buffer.write(chunk)
        output.buffer.flush()


ExecuteCommandMode = Literal["hold", "flush_duplicate", "flush_main"]


async def execute_command(
    bash_command: str,
    *,
    target: IPv4Address | Port | None = None,
    timeout: float | None = None,
    mode: ExecuteCommandMode = "hold",
    lighthouse_private_key_path: FilePath = config.lighthouse_private_key_path,
    tcp_connection_timeout: int = config.tcp_connection_timeout,
    proxypi_user: str = config.proxypi_user,
    raise_exit_code: bool = True,
) -> tuple[str, timedelta]:
    """
    Executes command either on the host or on a node.
    Handles the inputs and outputs and the timeout.

    Args:
        bash_command (str): To give as ready to use, the function encapsulates in `bash -lc '...'`.
        target (IPv4Address | Port | None): If None, runs on the host.
        timeout (float | None): If None, runs without timeout. In seconds.
        mode (ExecuteCommandMode): Description, optional (default: "hold").
        lighthouse_private_key_path (FilePath): Description, optional (default: config.lighthouse_private_key_path).
        tcp_connection_timeout (int): Description, optional (default: config.tcp_connection_timeout).
        proxypi_user (str): Description, optional (default: config.proxypi_user).
        raise_exit_code (bool): If set to `True`, will raise an error if the command exit with a non zero code. (default: True).

    Returns:
        tuple[str, timedelta]: Description.

    Raises:
        ValueError: Description.
        KeyError: Description.
        RuntimeError: Description.
        TimeoutError: Description.
        ExitCodeError: Description.
    """

    async def wait_for(coro: Awaitable[T]) -> T:
        """
        NOT THE ASYNCIO IMPLEMENTATION!
        WRAPPER!
        """
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout)

    if mode in ["hold", "flush_duplicate"]:
        stdout = asyncio.subprocess.PIPE
        stderr = asyncio.subprocess.PIPE
    elif mode == "flush_main":
        stdout = None
        stderr = None
    else:
        raise ValueError(f"invalid mode: {mode!r}")

    bash_command = f"bash -lc {quote(bash_command)}"

    if target is not None:
        conn = [
            "ssh",
            "-tt",
            "-i",
            str(lighthouse_private_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"ConnectTimeout={tcp_connection_timeout}",
        ]
        if isinstance(target, int):
            if target not in listen_ports():
                raise KeyError(f"given {target} is not currently in use") from None
            conn.extend(
                [
                    "-p",
                    str(target),
                    f"{proxypi_user}@localhost",
                ]
            )
        elif isinstance(target, IPv4Address):
            conn.append(f"{proxypi_user}@{target}")

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

    start_beacon = datetime.now(UTC)
    end_beacon: datetime

    try:
        if mode == "hold":
            command_stdout, command_stderr = await wait_for(proc.communicate())
            end_beacon = datetime.now(UTC)

            command_stdout = command_stdout.decode()
            command_stderr = command_stderr.decode()

        elif mode == "flush_duplicate":
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []
            _ = await wait_for(
                asyncio.gather(
                    __read_stream(proc.stdout, sys.stdout, stdout_chunks),
                    __read_stream(proc.stderr, sys.stderr, stderr_chunks),
                    proc.wait(),
                )
            )

            end_beacon = datetime.now(UTC)

            command_stdout = b"".join(stdout_chunks).decode()
            command_stderr = b"".join(stderr_chunks).decode()
        elif mode == "flush_main":
            _ = await wait_for(proc.wait())

            end_beacon = datetime.now(UTC)

            command_stdout = ""
            command_stderr = ""

        if proc.returncode is None:
            raise RuntimeError("proc does not have a returncode")
        elif raise_exit_code and proc.returncode != 0:
            raise ExitCodeError(
                bash_command=bash_command,
                host=target or None,
                returncode=proc.returncode,
                stderr=command_stderr.strip(),
            )

        return (
            command_stdout,
            end_beacon - start_beacon,
        )

    except TimeoutError:
        proc.terminate()
        _ = await proc.wait()
        raise TimeoutError(
            f"`{bash_command}` timed out after {timeout}s on {target or 'localhost'}`"
        ) from None

    finally:
        if proc.returncode is None:
            proc.terminate()
            _ = await proc.wait()
