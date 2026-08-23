import asyncio

from typer import Typer

import proxypi.commands.ssh
from proxypi.common.core import listen

app = Typer()


@app.command()
def test_listen():
    print(listen())


app.add_typer(proxypi.commands.ssh.app, name="ssh")


if __name__ == "__main__":
    app()
