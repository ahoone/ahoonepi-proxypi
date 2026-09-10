from typing import Annotated

from typer import Argument, Context, Option

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


def complete_proxy_ids(ctx: Context, incomplete: str) -> list[str]:
    selected: list[str] = ctx.params.get("proxy_ids") or []

    return [
        str(proxy_id)
        for proxy_id in listen_proxy_ids()
        if str(proxy_id).startswith(incomplete) and str(proxy_id) not in selected
    ]


ProxyIDArgument = Annotated[
    int,
    Argument(min=2, max=config.network_size, autocompletion=complete_proxy_id),
]


ProxyIDsOption = Annotated[
    list[int], Option(min=2, max=config.network_size, autocompletion=complete_proxy_ids)
]
