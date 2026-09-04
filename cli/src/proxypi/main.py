from typer import Typer

import proxypi.commands.deploy
import proxypi.commands.dev
import proxypi.commands.init
import proxypi.commands.ssh

app = Typer()


app.add_typer(proxypi.commands.ssh.app, name="ssh")
app.add_typer(proxypi.commands.deploy.app, name="deploy")
app.add_typer(proxypi.commands.init.app, name="init")
app.add_typer(proxypi.commands.dev.app, name="dev")

if __name__ == "__main__":
    app()
