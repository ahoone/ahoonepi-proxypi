from typer import Typer

import proxypi.commands.deployment
import proxypi.commands.install
import proxypi.commands.ssh

app = Typer()


app.add_typer(proxypi.commands.ssh.app, name="ssh")
app.add_typer(proxypi.commands.deployment.app, name="deployment")
app.add_typer(proxypi.commands.install.app, name="install")


if __name__ == "__main__":
    app()
