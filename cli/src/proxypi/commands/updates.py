import typer

app = typer.Typer()


@app.command()
def update_software_version():
    raise NotImplementedError


@app.command()
def apt_update():
    raise NotImplementedError


@app.command()
def apt_upgrade():
    raise NotImplementedError
