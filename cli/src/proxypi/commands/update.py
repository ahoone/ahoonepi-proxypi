import asyncio

from proxypi.common.core import execute_command
from proxypi.common.options import NodeIDOption
from proxypi.common.types import Port, node_id_to_port


async def git(target: Port | None, *args: str) -> str:
    bash_command = f"git {' '.join(args)}"
    response, _ = await execute_command(bash_command, target=target, mode="hold")
    return response


def update(node_id: NodeIDOption):
    target = None if node_id == 1 else node_id_to_port(node_id)

    asyncio.run()
