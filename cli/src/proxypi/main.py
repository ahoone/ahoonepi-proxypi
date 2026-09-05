from typer import Typer

from proxypi.commands.conf import conf
from proxypi.commands.connect import connect
from proxypi.commands.copy_keys import copy_keys
from proxypi.commands.deps import deps
from proxypi.commands.load import load
from proxypi.commands.ping import ping
from proxypi.commands.tests import tests
from proxypi.commands.venv import venv

app = Typer()

app.command()(conf)
app.command()(connect)
app.command()(copy_keys)
app.command()(deps)
app.command()(load)
app.command()(ping)
app.command()(tests)
app.command()(venv)

if __name__ == "__main__":
    app()
