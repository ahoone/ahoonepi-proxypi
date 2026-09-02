from typer import Typer

import proxypi.commands.deployment
import proxypi.commands.install
import proxypi.commands.ssh
from proxypi.common.config import PROJECT_ROOT, config
from proxypi.common.core import listen_proxyids

app = Typer()


# @app.command()
# def test_listen():
#     print(listen())


app.add_typer(proxypi.commands.ssh.app, name="ssh")
app.add_typer(proxypi.commands.deployment.app, name="deployment")
app.add_typer(proxypi.commands.install.app, name="install")


@app.command()
def listen_ids():
    print(listen_proxyids())


@app.command()
def display_config():
    print(
        f"project-dir: {PROJECT_ROOT}",
    )


if __name__ == "__main__":
    app()
