import asyncio
from typing import Annotated

from pydantic import BaseModel
from typer import Option

from proxypi.common.config import config
from proxypi.common.core import execute_command, listen_proxy_ids
from proxypi.common.options import ProxyIDsOption
from proxypi.common.types import CommandResponse, ProxyID
from proxypi.common.utils import gather_with_progress, print_table, to_table


class SwarmRow(BaseModel):
    port: ProxyID
    success: bool


def swarm(
    bash_command: str,
    timeout: Annotated[
        int | None,
        Option(
            help="timeout in seconds. if not set, no timeout will enclose the command"
        ),
    ] = None,
    proxy_ids: ProxyIDsOption | None = None,
):
    """
    Executes bash instructions on targeted proxies.
    """
    targets = listen_proxy_ids() if not proxy_ids else proxy_ids

    concurrent_conn = config.concurrent_conn

    coros = [
        execute_command(
            bash_command, target=target, timeout=timeout, raise_exit_code=False
        )
        for target in targets
    ]
    responses: list[CommandResponse] = asyncio.run(
        gather_with_progress(*coros, concurrent_conn=concurrent_conn)
    )
    rows = [SwarmRow(port=r.target, success=r.returncode == 0) for r in responses]
    table = to_table(rows)
    print_table(table)
