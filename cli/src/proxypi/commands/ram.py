import asyncio

from pydantic import BaseModel

from proxypi.common.core import execute_command
from proxypi.common.options import NodeIDArgument
from proxypi.common.types import Port, node_id_to_port
from proxypi.common.utils import run_with_spinner


class RamResponse(BaseModel):
    ram_specs: str
    ram_usage: float


def ram(node_id: NodeIDArgument):
    """
    Twin of `info` for ram information. Legacy.
    """

    target = None if node_id == 1 else node_id_to_port(node_id)

    @run_with_spinner("Requesting...")
    async def inner() -> None:

        response = (await execute_command("free", target=target)).stdout

        first_row = response.split("\n")[1].split()

        model = RamResponse(
            ram_specs=f"{int(first_row[1]) // 1024**2}Gi",
            ram_usage=int(first_row[3]) / int(first_row[2]) * 100,
        )
        print(model.model_dump(mode="json"))

    asyncio.run(inner())
