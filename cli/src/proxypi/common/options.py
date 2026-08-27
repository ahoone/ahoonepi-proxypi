from typing import Annotated

import typer

from proxypi.common.core import listen


def complete_port(incomplete: str) -> list[str]:
    return [str(port) for port in listen() if str(port).startswith(incomplete)]


PortOption = Annotated[
    int | None,
    typer.Option(
        min=0,
        max=2**16 - 1,
        autocompletion=complete_port,
    ),
]
