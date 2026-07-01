import asyncio
import datetime
import os
import subprocess
import threading
from typing import Any, AsyncGenerator, BinaryIO, Dict, List, Literal, Set, Tuple

import zendriver as uc
from Config import Config
from core.schemas import BotSpottedError, GetRequest
from engine.detection import herobrine_is_here
from engine.erholungszeit import erholungszeit
from engine.score import score

DISPLAY_DEPTH = 24
JPEG_MARKER_START = b"\xff\xd8\xff"
JPEG_MARKER_END = b"\xff\xd9"
MAXIMUM_SIZE_ERROR_MESSAGE = 256
SETTLING_WAIT_TIME_COMPLETE = 1  # seconds
SETTLING_WAIT_TIME_INTERACTIVE = 3  # seconds
STREAM_CHUNK_SIZE = 2**14  # 16,384 bits
STREAM_FPS = 12
STREAM_QUALITY = 15  # 2=best 31=worst
TIMEOUT_TERMINATE_DISPLAY = 6  # seconds
TIMEOUT_TERMINATE_UNPACKING = 6  # seconds
TIMEOUT_TERMINATE_STREAM = 6  # seconds


class Browser:
    """
    maybe a lock should be used to avoid multiple simultaneous call
    are made to the get method
    """

    display = 100  # First Xvfb (instead of 99)

    def __init__(self) -> None:
        self.window_size: Tuple[int, int] = None
        self.display: str = None
        self.__display_process = None
        self.__driver = None
        self.__streaming_process = None
        self.__unpacking_frames_process = None
        self.__latest_frame: bytes = b""
        self.__new_frame_available: asyncio.Event = asyncio.Event()
        self.__killing_event = asyncio.Event()
        self.created_at: datetime.datetime = None
        self.expires_at: datetime.datetime = None
        self.browsing_history: List[Dict] = []
        self.__get_lock: asyncio.Lock = asyncio.Lock()
        self.spotted: bool = False
        self.erholungszeit: datetime.datetime = None  # recovery period after a request

    @classmethod
    async def create(
        cls,
        lifespan_in_seconds: int,
        window_size: Tuple[int, int],
    ) -> "Browser":
        instance = cls()
        await instance.__initialize(
            lifespan_in_seconds,
            window_size,
        )
        return instance

    async def __initialize(
        self,
        lifespan_in_seconds: int,
        window_size: Tuple[int, int],
    ) -> None:
        self.window_size = window_size
        self.__create_display()
        self.__driver = await self.__create_driver()
        self.created_at = datetime.datetime.now()
        self.expires_at = self.created_at + datetime.timedelta(
            seconds=lifespan_in_seconds
        )
        self.__create_unpacking_frames_process()
        self.erholungszeit = datetime.datetime.now()

    def __create_display(self) -> None:
        self.display = f":{Browser.display}"
        Browser.display += 1

        command = [
            "Xvfb",
            self.display,
            "-screen",
            "0",
            f"{self.window_size[0]}x{self.window_size[1]}x{DISPLAY_DEPTH}",
        ]

        self.__display_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    async def __create_driver(self) -> None:
        os.environ["DISPLAY"] = self.display
        return await uc.start(
            headless=False,  # If headerless, Cloudflare spots us.
            browser_args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                f"--window-size={self.window_size[0]},{self.window_size[1]}",
                "--window-position=0,0",
            ],  # If images are blocked, Cloudflare spots us.
            sandbox=False,
            env={**os.environ},
        )

    def __create_streaming_process(self) -> None:
        if self.__streaming_process:
            return

        command = [
            "ffmpeg",
            "-loglevel",
            "quiet",
            "-f",
            "x11grab",
            "-framerate",
            str(STREAM_FPS),
            "-video_size",
            f"{self.window_size[0]}x{self.window_size[1]}",
            "-i",
            self.display,
            "-f",
            "mjpeg",
            "-q:v",
            str(STREAM_QUALITY),
            "-flush_packets",
            "1",
            "pipe:1",
        ]

        self.__streaming_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "DISPLAY": self.display},
        )

    @staticmethod
    def __unpack_frames(stream: BinaryIO) -> bytes:
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

    def __create_unpacking_frames_process(self) -> None:
        if not self.__streaming_process:
            self.__create_streaming_process()

        def __unpack_through_thread() -> None:
            for frame in self.__unpack_frames(self.__streaming_process.stdout):
                self.__latest_frame = frame
                self.__new_frame_available.set()

        self.__unpacking_frames_process = threading.Thread(
            target=__unpack_through_thread,
            daemon=True,
        )
        self.__unpacking_frames_process.start()

    def status(self) -> Literal["idle", "requesting", "spotted", "waiting"]:
        if self.spotted:
            return "spotted"
        elif self.__get_lock.locked():
            return "requesting"
        elif self.erholungszeit > datetime.datetime.now():
            return "waiting"
        else:
            return "idle"

    def score(self) -> float:
        return score(self.browsing_history)

    def remaining_lifespan(self) -> datetime.timedelta:
        return self.expires_at - datetime.datetime.now()

    def expired(self) -> bool:
        """
        true if EXPIRED and false if alive
        """
        return self.expires_at < datetime.datetime.now()

    async def stream(self) -> AsyncGenerator[bytes, Any]:
        while True:
            await self.__new_frame_available.wait()
            if self.__latest_frame:
                self.__new_frame_available.clear()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + self.__latest_frame + b"\r\n"
                )

    @staticmethod
    async def smart_wait(page) -> Literal["complete", "interactive", "loading"]:
        """
        tries to wait up for the complete status, but returns with any status after a certain waiting time
        """
        current_state = await page.evaluate("document.readyState")
        if current_state == "complete":
            pass
        elif current_state == "interactive":
            try:
                await page.wait_for_ready_state(
                    until="complete", timeout=SETTLING_WAIT_TIME_COMPLETE
                )
            except asyncio.TimeoutError:
                pass
        else:
            try:
                await page.wait_for_ready_state(
                    until="interactive", timeout=SETTLING_WAIT_TIME_INTERACTIVE
                )
            except asyncio.TimeoutError:
                pass
        current_state = await page.evaluate("document.readyState")
        return current_state

    async def get_or_abort(self, request: GetRequest) -> str:
        try:
            async with self.__get_lock:
                return await self.get(request)
        except asyncio.CancelledError:
            self.browsing_history.append(
                {
                    "url": request.url,
                    "status": "aborted",
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            return ""

    async def trigger_lazy_loading(self, page: uc.Tab) -> bool:
        """
        INCOMPLETE
        Should:
            - scroll down repeatedly
            - wait for network idle
            - wait for dom stabilization
            - very images are complete
            - no keywords like "skeleton", "anim_skeleton", "bg-c_skeleton"

        Returns:
            bool: True if achieved network inactivity in given time.
        """

        time_limit = datetime.datetime.now() + datetime.timedelta(
            seconds=Config.TIME_LIMIT_LAZY_LOADING,
        )
        # scroll_height = 0  # percentages of the screen height
        while datetime.datetime.now() < time_limit:
            await page.scroll_down(1000)
            await asyncio.sleep(4)
            return True

        return False

    async def get(self, request: GetRequest) -> str:
        """
        Moves the current page and captures its html content.

        Args:
            request (GetRequest): .

        Returns:
            str: The html code.

        Raises:
            BotSpottedError: .
        """

        access_record = {}

        delta = (self.erholungszeit - datetime.datetime.now()).total_seconds()
        if delta > 0.0:
            await asyncio.sleep(delta)

        try:
            page = await self.__driver.get(request.url, new_tab=False, new_window=False)
            access_record["page_state"] = await self.smart_wait(page)
            self.erholungszeit = datetime.datetime.now() + datetime.timedelta(
                milliseconds=erholungszeit()
            )
            html = await page.get_content()

            if herobrine_is_here(html):
                self.spotted = True
                raise BotSpottedError(html)
                # should also raise a html error to the broker

            if request.flag_lazy_loading:
                access_record["success_lazy_loading"] = await self.trigger_lazy_loading(
                    page
                )
                html = await page.get_content()

        except BotSpottedError as e:
            access_record.update(
                {
                    "url": request.url,
                    "status": "blocked",
                    "html": e.html,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            self.browsing_history.append(access_record)
            return ""

        except Exception as e:
            access_record.update(
                {
                    "url": request.url,
                    "status": "failed",
                    "error": str(e)[:MAXIMUM_SIZE_ERROR_MESSAGE],
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            self.browsing_history.append(access_record)
            return ""

        access_record.update(
            {
                "url": request.url,
                "status": "success",
                "content_length": len(html),
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )
        self.browsing_history.append(access_record)
        return html

    def __kill_streaming_process(self) -> None:
        if not self.__streaming_process:
            return
        self.__streaming_process.terminate()
        try:
            self.__streaming_process.wait(timeout=TIMEOUT_TERMINATE_STREAM)
        except subprocess.TimeoutExpired:
            self.__streaming_process.kill()
            self.__streaming_process.wait()
        self.__streaming_process = None

    def __kill_unpacking_frames_process(self) -> None:
        if not self.__unpacking_frames_process:
            return
        self.__unpacking_frames_process.join(timeout=TIMEOUT_TERMINATE_UNPACKING)

    def __close_display(self) -> None:
        """
        This version does not account for Xvfb creating its own child processes
        """
        if not self.__display_process:
            return
        self.__display_process.terminate()
        try:
            self.__display_process.wait(timeout=TIMEOUT_TERMINATE_DISPLAY)
        except subprocess.TimeoutExpired:
            self.__display_process.kill()
            self.__display_process.wait()
        self.__display_process = None

    async def kill(self) -> None:
        self.__kill_streaming_process()
        self.__kill_unpacking_frames_process()
        self.__close_display()
        asyncio.create_task(self.__driver.stop())  # probably never stopping
        # creates a zombie process
        # 999      4088371  0.0  0.0      0     0 ?        Z    Apr20   0:00 [chrome_crashpad] <defunct>
