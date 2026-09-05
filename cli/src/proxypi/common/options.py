from typing import Annotated

from typer import Argument, Option

from proxypi.common.config import config
from proxypi.common.core import listen_node_ids, listen_proxy_ids


def complete_node_id(incomplete: str) -> list[str]:
    return [
        str(node_id)
        for node_id in listen_node_ids()
        if str(node_id).startswith(incomplete)
    ]


NodeIDArgument = Annotated[
    int, Argument(min=1, max=config.network_size, autocompletion=complete_node_id)
]

NodeIDOption = Annotated[
    int, Option(min=1, max=config.network_size, autocompletion=complete_node_id)
]


def complete_proxy_id(incomplete: str) -> list[str]:
    return [
        str(proxy_id)
        for proxy_id in listen_proxy_ids()
        if str(proxy_id).startswith(incomplete)
    ]


ProxyIDArgument = Annotated[
    int,
    Argument(min=2, max=config.network_size, autocompletion=complete_proxy_id),
]
