import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def timed(awaitable: Awaitable[T]) -> tuple[T, float]:
    loop = asyncio.get_event_loop()
    start_time = loop.time()
    try:
        result = await awaitable
    except Exception as e:
        e.elapsed = loop.time() - start_time
        raise
    return result, loop.time() - start_time
