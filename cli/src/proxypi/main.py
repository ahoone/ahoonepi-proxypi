from typer import Typer

import proxypi.commands.deploy
import proxypi.commands.init
import proxypi.commands.ssh
from proxypi.commands.venv import venv

app = Typer()


app.add_typer(proxypi.commands.ssh.app, name="ssh")
app.add_typer(proxypi.commands.deploy.app, name="deploy")
app.add_typer(proxypi.commands.init.app, name="init")
app.command()(venv)


if __name__ == "__main__":
    app()
