import asyncio
from ipaddress import IPv6Address

from pydantic import BaseModel

from proxypi.common.core import execute_command
from proxypi.common.options import NodeIDArgument
from proxypi.common.types import Port, node_id_to_port
from proxypi.common.utils import run_with_spinner


class InfoResponse(BaseModel):
    hostname: str
    port: Port | None
    ipv6: IPv6Address


def info(node_id: NodeIDArgument):
    """
    Displays information on the given node as a json format used by the broker.
    """

    target = None if node_id == 1 else node_id_to_port(node_id)

    @run_with_spinner("Requesting...")
    async def inner() -> None:
        bash_command = (
            "printf '%s|%s' $(hostname) $(curl ifconfig.me 2>/dev/null || echo 'N/A')"
        )
        response, _ = await execute_command(bash_command, target=target)
        hostname, ipv6_address = response.split("|")

        model = InfoResponse(
            hostname=hostname,
            port=target,
            ipv6=IPv6Address(ipv6_address),
        )

        print(model.model_dump(mode="json"))

    asyncio.run(inner())
