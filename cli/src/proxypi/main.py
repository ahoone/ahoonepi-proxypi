from typer import Typer

from proxypi.commands.conf import conf
from proxypi.commands.connect import connect
from proxypi.commands.copy_keys import copy_keys
from proxypi.commands.deps import deps
from proxypi.commands.ping import ping
from proxypi.commands.sync import sync
from proxypi.commands.tests import tests
from proxypi.commands.venv import venv

app = Typer()

app.command()(conf)
app.command()(connect)
app.command()(copy_keys)
app.command()(deps)
app.command()(ping)
app.command()(sync)
app.command()(tests)
app.command()(venv)

if __name__ == "__main__":
    app()
