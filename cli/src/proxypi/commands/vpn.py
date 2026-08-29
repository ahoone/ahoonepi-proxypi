import typer

app = typer.Typer()


@app.command()
def ping():
    raise NotImplementedError


@app.command()
def load():
    """
    Loads the proxies' keys in the lighthouse's configuration file.
    """
    raise NotImplementedError
