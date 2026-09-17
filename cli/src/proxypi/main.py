from typing import Annotated

from typer import Context, Option, Typer

from proxypi.commands.conf import conf
from proxypi.commands.connect import connect
from proxypi.commands.copy_keys import copy_keys
from proxypi.commands.deploy import deploy
from proxypi.commands.deps import deps
from proxypi.commands.info import info
from proxypi.commands.ping import ping
from proxypi.commands.ram import ram
from proxypi.commands.status import status
from proxypi.commands.swarm import swarm
from proxypi.commands.sync import sync
from proxypi.commands.tests import tests
from proxypi.commands.venv import venv

app = Typer()

app.command()(conf)
app.command()(connect)
app.command()(copy_keys)
app.command()(deploy)
app.command()(deps)
app.command()(info)
app.command()(ping)
app.command()(ram)
app.command()(status)
app.command()(swarm)
app.command()(sync)
app.command()(tests)
app.command()(venv)


@app.callback()
def main(
    ctx: Context,
    verbose: Annotated[bool, Option("--verbose", "-v", help="")] = False,
    relative_path: Annotated[
        bool,
        Option(
            "--relative-path",
            help="Used to indicate the cli is launched from the project root, "
            + "and not as an stand alone package. "
            + "Intended to be used in development.",
    verbose: Annotated[
        bool,
        Option(
            "--verbose",
            "-v",
            help="Enables the live streaming of stdout to the terminal, if available.",
        ),
    ] = False,
):
    ctx.obj = {}
    ctx.obj["verbose"] = verbose


if __name__ == "__main__":
    app()
