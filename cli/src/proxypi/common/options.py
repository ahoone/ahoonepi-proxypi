from typing import Annotated

import typer

from proxypi.common.config import config
from proxypi.common.constants import RANGE_PORTS
from proxypi.common.core import listen_ports, listen_proxyids


def complete_port(incomplete: str) -> list[str]:
    return [str(port) for port in listen_ports() if str(port).startswith(incomplete)]


port_option: typer.Option = typer.Option(
    min=RANGE_PORTS[0],
    max=RANGE_PORTS[1],
    autocompletion=complete_port,
)


PortOption = Annotated[
    int,
    port_option,
]

PortOrHostOption = Annotated[
    int | None,
    port_option,
]


def complete_proxy_id(incomplete: str) -> list[str]:
    return [
        str(proxy_id)
        for proxy_id in listen_proxyids()
        if str(proxy_id).startswith(incomplete)
    ]


ProxyIDArgument = Annotated[
    int,
    typer.Argument(min=2, max=config.network_size, autocompletion=complete_proxy_id),
]
