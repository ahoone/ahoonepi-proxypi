import asyncio
import threading
from collections.abc import AsyncGenerator, Generator
from typing import Any, BinaryIO

from core.Streamer import Streamer

STREAM_CHUNK_SIZE = 2**14  # 16,384 bits
JPEG_MARKER_START = b"\xff\xd8\xff"
JPEG_MARKER_END = b"\xff\xd9"
TIMEOUT_KILL = 6  # seconds


class FrameUnpacker:
    __latest_frame: bytes
    __new_frame_available: asyncio.Event

    @staticmethod
    def __unpack_frames(stream: BinaryIO) -> Generator[bytes, Any, Any]:
        buffer = bytearray()
        while chunk := stream.read(STREAM_CHUNK_SIZE):
            buffer.extend(chunk)
            while True:
                start = buffer.find(JPEG_MARKER_START)
                if start == -1:
                    buffer.clear()
                    break
                end = buffer.find(JPEG_MARKER_END, start)
                if end == -1:
                    if start > 0:
                        del buffer[:start]
                    break
                end += len(JPEG_MARKER_END)
                frame = bytes(buffer[start:end])
                yield frame
                del buffer[:end]

    def __init__(self, streamer: Streamer) -> None:
        """
        Starts the unpacking thread.
        """
        self.__new_frame_available = asyncio.Event()

        stdout = streamer.process.stdout
        if not stdout:
            raise ValueError("streamer.process.stdout is None")

        def __unpack_through_thread() -> None:
            for frame in self.__unpack_frames(stdout):
                self.__latest_frame = frame
                self.__new_frame_available.set()

        self.__process = threading.Thread(
            target=__unpack_through_thread,
            daemon=True,
        )
        self.__process.start()

    async def stream(self) -> AsyncGenerator[bytes, Any]:
        while True:
            await self.__new_frame_available.wait()
            if self.__latest_frame:
                self.__new_frame_available.clear()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + self.__latest_frame + b"\r\n"
                )

    def kill(self) -> None:
        self.__process.join(timeout=TIMEOUT_KILL)
