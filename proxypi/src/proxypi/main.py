from typer import Typer

from proxypi.Config import config

app = Typer()


@app.command()
def hello(name: str):
    print(f"hello {name}")


@app.command()
def goodbye(name: str, formal: bool = False):
    if formal:
        print(f"bye mister {name}")
    else:
        print(f"bye {name}")


@app.command()
def print_config():
    print(config)


if __name__ == "__main__":
    app()
