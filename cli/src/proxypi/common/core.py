import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from ipaddress import IPv4Address
from shlex import quote
from typing import Literal, TypeVar

from pydantic import FilePath

from proxypi.common.config import config
from proxypi.common.listen import listen_ports
from proxypi.common.stdout import console_stream, holds_terminal
from proxypi.common.types import (
    CommandResponse,
    ExitCodeError,
    TTarget,
    port_to_node_id,
)

T = TypeVar("T")


ExecuteCommandMode = Literal["hold", "flush"]


async def host_has_sudo() -> bool:
    proc = await asyncio.create_subprocess_exec(
        "sudo",
        "-n",
        "true",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await proc.wait() == 0


async def host_acquires_sudo() -> None:
    async with holds_terminal():
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-v", stdin=None, stdout=None, stderr=None
        )
        if await proc.wait() != 0:
            raise PermissionError("Failed to acquire sudo privileges.")


async def execute_command(
    bash_command: str,
    *,
    target: TTarget = None,
    timeout: float | None = None,
    mode: ExecuteCommandMode = "hold",
    capture_stdout: bool = True,
    raise_exit_code: bool = True,
    force_tty_remote: bool = True,
    lighthouse_private_key_path: FilePath = config.lighthouse_private_key_path,
    tcp_connection_timeout: int = config.tcp_connection_timeout,
    proxypi_user: str = config.proxypi_user,
) -> CommandResponse[TTarget]:
    """
    Executes command either on the host or a proxy.
    Handles the inputs and outputs and the timeout.
    Does not handle stdin (always set to `devnull`).
    Can ask for the sudo rights on host if the command requires it.

    Args:
        bash_command (str): To give as ready to use, the function encapsulates in `bash -lc '...'`.
        target (TTarget): If None, runs on the host (default: None).
        timeout (float | None): If None, runs without timeout. Given in seconds (default: None).
        mode (ExecuteCommandMode): If `hold`: does not stream the output. If `flush`: stream the output to stdout (default: "hold").
        raise_exit_code (bool): If set to `True`, will raise an error if the command exit with a non zero code (default: True).
        force_tty_remote (bool): Force the proxies to use enhance logs, but may fail for some program (see `proxypi.dependencies.uv`) (default: True).
        lighthouse_private_key_path (FilePath): Description, optional (default: config.lighthouse_private_key_path).
        tcp_connection_timeout (int): Description, optional (default: config.tcp_connection_timeout).
        proxypi_user (str): Description, optional (default: config.proxypi_user).

    Returns:
        CommandResponse[TTarget]: Description.

    Raises:
        KeyError: Description.
        RuntimeError: Description.
        ExitCodeError: Description.
        TimeoutError: Description.
    """

    async def wait_for(coro: Awaitable[T]) -> T:
        """
        NOT THE ASYNCIO IMPLEMENTATION!
        WRAPPER!
        """
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout)

    if target is None and "sudo" in bash_command and not await host_has_sudo():
        print(f"Sudo rights are required on host for command:\n{bash_command}")
        await host_acquires_sudo()

    bash_command = f"bash -lc {quote(bash_command)}"

    if target is not None:
        conn = [
            "ssh",
            "-n",
            "-i",
            str(lighthouse_private_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"ConnectTimeout={tcp_connection_timeout}",
        ]
        conn.append("-tt" if force_tty_remote else "-T")

        if isinstance(target, int):
            if target not in listen_ports():
                raise KeyError(
                    f"given port `{target}` (node_id: {port_to_node_id(target)}) is not currently in use"
                ) from None
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
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_shell(
            bash_command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    if not proc.stdout:
        raise RuntimeError("proc.stdout was not set")
    if not proc.stderr:
        raise RuntimeError("proc.stderr was not set")

    command_stdout: str | bytes
    command_stderr: str | bytes

    start_beacon = datetime.now(UTC)
    end_beacon: datetime

    try:
        if mode == "hold":
            if capture_stdout:
                command_stdout, command_stderr = await wait_for(proc.communicate())
                end_beacon = datetime.now(UTC)

                command_stdout = command_stdout.decode()
                command_stderr = command_stderr.decode()
            else:
                _ = await wait_for(proc.wait())
                end_beacon = datetime.now(UTC)

                command_stdout = ""
                command_stderr = ""

        elif mode == "flush":
            tag = str(target) if target is not None else "localhost"

            if capture_stdout:
                stdout_chunks: list[str] = []
                stderr_chunks: list[str] = []

                _ = await wait_for(
                    asyncio.gather(
                        console_stream(proc.stdout, tag, stdout_chunks),
                        console_stream(proc.stderr, tag, stderr_chunks),
                        proc.wait(),
                    )
                )

                end_beacon = datetime.now(UTC)

                command_stdout = "".join(stdout_chunks)
                command_stderr = "".join(stderr_chunks)

            else:
                _ = await wait_for(
                    asyncio.gather(
                        console_stream(proc.stdout, tag),
                        console_stream(proc.stderr, tag),
                        proc.wait(),
                    )
                )

                end_beacon = datetime.now(UTC)

                command_stdout = ""
                command_stderr = ""

        if proc.returncode is None:
            raise RuntimeError("proc does not have a returncode")
        elif proc.returncode == 1 and "sudo: a password is required" in command_stderr:
            raise RuntimeError("the remotes should not ask for inputs")
        elif raise_exit_code and proc.returncode != 0:
            raise ExitCodeError(
                bash_command=bash_command,
                host=target or None,
                returncode=proc.returncode,
                stderr=command_stderr.strip(),
            )

        return CommandResponse(
            target=target,
            bash_command=bash_command,
            returncode=proc.returncode,
            stdout=command_stdout,
            stderr=command_stderr,
            duration=end_beacon - start_beacon,
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
