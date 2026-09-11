import asyncio
from typing import TextIO

from rich.console import Console
from rich.progress import Progress

STDOUT_LOCK: asyncio.Lock = asyncio.Lock()
STDOUT_HOLDER: Progress | None = None
STDOUT_HOLDER_USERS: int = 0
STDOUT_HOLDER_LOCK: asyncio.Lock = asyncio.Lock()
CONSOLE_LOCK: asyncio.Lock = asyncio.Lock()

console = Console()

async def __format_stream(
    stream: asyncio.StreamReader,
    output: TextIO,
    console_lock: asyncio.Lock = CONSOLE_LOCK,
) -> None:
    current_line: bytes = b""
    while chunk := await stream.read(2**12):
        lines = chunk.split(b"\n")
        if current_line:
            lines[0] = current_line + lines[0]
            current_line = b""
        if not lines[-1].endswith(b"\n"):
            current_line = lines[-1]
            lines.pop()
        async with console_lock:
            for line in lines:
