import asyncio
import subprocess
from typing import ClassVar

DISPLAY_DEPTH = 24
TIMEOUT_KILL = 6  # seconds


class Display:
    display: str
    __display_process: subprocess.Popen
    window_size: tuple[int, int]

    __origin_display: ClassVar[int] = 99  # we use [100; +inf[
    __cls_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def get_display_id(cls) -> str:
        async with cls.__cls_lock:
            cls.__origin_display += 1
            return f":{cls.__origin_display}"

    @classmethod
    async def create(cls, window_size: tuple[int, int]) -> "Display":
        instance = cls()
        await instance.__initialize(window_size)
        return instance

    async def __initialize(self, window_size: tuple[int, int]) -> None:
        self.display = await Display.get_display_id()
        self.window_size = window_size

        command = [
            "Xvfb",
            self.display,
            "-screen",
            "0",
            f"{window_size[0]}x{window_size[1]}x{DISPLAY_DEPTH}",
        ]

        self.__display_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def kill(self) -> None:
        """
        This version does not account for Xvfb creating its own child processes
        """
        if not self.__display_process:
            return
        self.__display_process.terminate()
        try:
            self.__display_process.wait(timeout=TIMEOUT_KILL)
        except subprocess.TimeoutExpired:
            self.__display_process.kill()
            self.__display_process.wait(timeout=TIMEOUT_KILL)
