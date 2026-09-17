import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from rich.console import Console
from rich.progress import Progress

from proxypi.common.types import AsyncFunc

STDOUT_LOCK: asyncio.Lock = asyncio.Lock()
TERMINAL_HOLDER: Progress | None = None
TERMINAL_LOCK: asyncio.Lock = asyncio.Lock()
CONSOLE = Console()

P = ParamSpec("P")
T = TypeVar("T")


def set_terminal_holder(progress: Progress) -> None:
    global TERMINAL_HOLDER
    if TERMINAL_HOLDER is not None:
        raise RuntimeError(
            "there should not be 2 unrelated progress, this case should have been blocked by decorator `run_on_stdout`"
        )
    TERMINAL_HOLDER = progress


def drop_terminal_holder() -> None:
    global TERMINAL_HOLDER
    TERMINAL_HOLDER = None


def console_print(*args: Any, **kwargs: Any) -> None:
    CONSOLE.print(*args, **kwargs)


async def async_console_print(*args: Any, **kwargs: Any) -> None:
    async with TERMINAL_LOCK:
        console_print(*args, **kwargs)


async def console_stream(
    stream: asyncio.StreamReader,
    tag: str,
    duplicata: list[str] | None = None,
) -> None:
    async for line in stream:
        line = line.strip()
        if line == b"":
            continue
        decoded_line = line.decode(errors="replace")
        await async_console_print(f"[bold cyan]{tag: <15}[/] | {decoded_line}")
        if duplicata is not None:
            duplicata.append(decoded_line)


@asynccontextmanager
async def holds_terminal():
    """
    Give to the current task the exclusive control of the terminal.
    """

    async with TERMINAL_LOCK:
        holder = TERMINAL_HOLDER

        if holder is not None:
            holder.stop()
        try:
            yield
        finally:
            if holder is not None:
                holder.start()


def run_on_stdout() -> Callable[[AsyncFunc[P, T]], AsyncFunc[P, T]]:
    """
    Decorates a function to mark it runs using stdout.
    Useful for rich's renderables.
    """

    def decorator(coro: AsyncFunc[P, T]) -> AsyncFunc[P, T]:

        @wraps(coro)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if STDOUT_LOCK.locked():
                raise RuntimeError(
                    "Multiple tasks should not try to write simultaneously to stdout"
                )
            async with STDOUT_LOCK:
                return await coro(*args, **kwargs)

        return wrapper

    return decorator
