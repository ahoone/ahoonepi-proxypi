import asyncio
from contextlib import asynccontextmanager
import datetime
from fastapi import FastAPI, status, Request, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
import ipaddress
from math import exp
import numpy as np
import os
from pydantic import BaseModel
import subprocess
import sys
import threading
from typing import (
    Tuple,
    List,
    Dict,
    Callable,
    Optional,
    Union,
    BinaryIO,
    Any,
    Literal,
    AsyncGenerator,
    Set,
)
import zendriver as uc

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "SCRAPER" in NODE_ROLE, "The node should be a scraper to launch this image"


BACKGROUND_UPDATE_PERIOD = 1  # seconds
BROWSER_DEFAULT_ID = "default"
BROWSER_DEFAULT_LIFESPAN = 3600  # 1 hour in seconds
BROWSER_DEFAULT_WINDOW = [1920, 1080]
DISPLAY_DEPTH = 24
DISPLAY_CLOSE_TIMEOUT = 6  # seconds
ERHOLUNGSZEIT_MINIMUM = 2000  # milliseconds
ERHOLUNGSZEIT_MEAN = 5000  # milliseconds
ERHOLUNGSZEIT_SPREAD = 0.5  # variance
ERHOLUNGSZEIT_REFRESH_PERIOD = 0.1  # seconds
JPEG_MARKER_START = b"\xff\xd8\xff"
JPEG_MARKER_END = b"\xff\xd9"
LIFESPAN_BUFFER_GET_REQUEST = 5  # seconds
MAXIMUM_SIZE_HTML = (
    2**13
)  # =8,192 based on manual tests, cloudflare pages are 4456 and 5620 characters
MAXIMUM_SIZE_ERROR_MESSAGE = 256
MAX_INSTANCES_PER_SCRAPER = 4
RETRY_PERIOD_KILLING_BROWSER = 0.1  # seconds
SCORE_PARAMETER_LAMBDA = 0.5
SETTLING_WAIT_TIME_COMPLETE = 1  # seconds
SETTLING_WAIT_TIME_INTERACTIVE = 3  # seconds
STREAM_CHUNK_SIZE = 2**14  # 16,384 bits
STREAM_CLOSE_TIMEOUT = 6  # seconds
STREAM_FPS = 12
STREAM_QUALITY = 15  # 2=best 31=worst
UNPACKING_CLOSE_TIMEOUT = 6  # seconds

THRESHOLD_ARTIFACTS_DETECTION = (
    2  # number of artifacts required to be considered spotted (inclusive)
)
CLOUDFLARE_ARTIFACTS = [
    "Cloudflare",
    "Just a moment...",
    "challenge-error-text",
    "/cdn-cgi/challenge-platform",
    "Why have I been blocked?",
    "You are unable to access",
]


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


# class Profile:
# Should be sent by the Broker
#     def __init__(self) -> None:
#         self.mouse_movements = None
#         self.scrolling_speed = None


class BotSpottedError(Exception):
    def __init__(self, html: str):
        self.html: str = html
        super().__init__("spotted by anti bot")


class NewInstanceRequest(BaseModel):
    instance_id: str = BROWSER_DEFAULT_ID
    lifespan_in_seconds: int = BROWSER_DEFAULT_LIFESPAN
    window_size: Union[List[int], Tuple[int, int]] = BROWSER_DEFAULT_WINDOW


class KillRequest(BaseModel):
    instance_id: str


class GetRequest(BaseModel):
    instance_id: str
    url: str


class Browser:

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
        browser = cls()
        await browser.__initialize(
            lifespan_in_seconds,
            window_size,
        )
        return browser

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
        def cost_function(access_record: dict) -> float:
            """
            density function of the exponential law
            too unexponential
            """
            time_elapsed = (
                datetime.datetime.now()
                - datetime.datetime.fromisoformat(access_record["timestamp"])
            ).total_seconds()
            return SCORE_PARAMETER_LAMBDA * exp(-time_elapsed * SCORE_PARAMETER_LAMBDA)

        return sum(
            [cost_function(access_record) for access_record in self.browsing_history]
        )

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

    def herobrine_is_here(self, html) -> bool:
        """
        analyze page.html to check if we were spotted by herobrine
        automatically updates the attribute spotted
        """
        if (
            sum([1 for artifact in CLOUDFLARE_ARTIFACTS if artifact in html])
            >= THRESHOLD_ARTIFACTS_DETECTION
        ):
            self.spotted = True
            return True
        return False

    async def get_or_abort(self, url: str) -> str:
        try:
            async with self.__get_lock:
                return await self.get(url)
        except asyncio.CancelledError:
            self.browsing_history.append(
                {
                    "url": url,
                    "status": "aborted",
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            return ""

    async def get(self, url: str) -> str:
        def erholungszeit() -> int:
            """
            return waiting time in milliseconds
            """
            return max(
                ERHOLUNGSZEIT_MINIMUM,
                np.random.normal(loc=ERHOLUNGSZEIT_MEAN, scale=ERHOLUNGSZEIT_SPREAD),
            )

        access_record = {}

        while self.erholungszeit and self.erholungszeit > datetime.datetime.now():
            await asyncio.sleep(ERHOLUNGSZEIT_REFRESH_PERIOD)

        try:
            page = await self.__driver.get(url)
            access_record["page_state"] = await self.smart_wait(page)
            self.erholungszeit = datetime.datetime.now() + datetime.timedelta(
                milliseconds=erholungszeit()
            )
            html = await page.get_content()

            if self.herobrine_is_here(html):
                raise BotSpottedError(html)
                # should also raise a html error to the broker

            access_record.update(
                {
                    "url": url,
                    "status": "success",
                    "content_length": len(html),
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            self.browsing_history.append(access_record)
            return html

        except BotSpottedError as e:
            access_record.update(
                {
                    "url": url,
                    "status": "blocked",
                    "html": e.html[:MAXIMUM_SIZE_HTML],
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            self.browsing_history.append(access_record)
            return ""

        except Exception as e:
            access_record.update(
                {
                    "url": url,
                    "status": "failed",
                    "error": str(e)[:MAXIMUM_SIZE_ERROR_MESSAGE],
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
            self.browsing_history.append(access_record)
            return ""

    def __kill_streaming_process(self) -> None:
        if not self.__streaming_process:
            return
        self.__streaming_process.terminate()
        try:
            self.__streaming_process.wait(timeout=STREAM_CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.__streaming_process.kill()
            self.__streaming_process.wait()
        self.__streaming_process = None

    def __kill_unpacking_frames_process(self) -> None:
        if not self.__unpacking_frames_process:
            return
        self.__unpacking_frames_process.join(timeout=UNPACKING_CLOSE_TIMEOUT)

    def __close_display(self) -> None:
        """
        This version does not account for Xvfb creating its own child processes
        """
        if not self.__display_process:
            return
        self.__display_process.terminate()
        try:
            self.__display_process.wait(timeout=DISPLAY_CLOSE_TIMEOUT)
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


class Scraper:

    def __init__(self) -> None:
        self.browsers: Dict[str, Browser] = {}
        self.__browser_active_tasks: Dict[str, Set[asyncio.Task]] = {}

    def browser_exists(self, instance_id: str) -> bool:
        return instance_id in self.browsers.keys()

    async def new_instance(self, request: Optional[NewInstanceRequest]) -> None:
        self.browsers[request.instance_id] = await Browser.create(
            request.lifespan_in_seconds, request.window_size
        )
        self.__browser_active_tasks[request.instance_id] = set()

    async def get(self, request: GetRequest) -> str:
        task = asyncio.create_task(
            self.browsers[request.instance_id].get_or_abort(request.url)
        )
        self.__browser_active_tasks[request.instance_id].add(task)
        try:
            return await task
        finally:
            self.__browser_active_tasks[request.instance_id].discard(task)

    async def update(self) -> None:
        expired = [
            self.kill(instance_id)
            for instance_id, browser in self.browsers.items()
            if browser.expired()
        ]
        await asyncio.gather(*expired)

    async def cancel_browser_tasks(self, instance_id: str) -> None:
        tasks = self.__browser_active_tasks[instance_id]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=False)

    async def kill(self, instance_id: str) -> None:
        await self.cancel_browser_tasks(instance_id)
        await self.browsers[instance_id].kill()
        del self.browsers[instance_id]
        del self.__browser_active_tasks[instance_id]

    async def terminate(self) -> None:
        kills = [browser.kill() for browser in self.browsers.values()]
        await asyncio.gather(*kills)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    # ipaddress.ip_network("10.0.0.0/24"),   # VPN network
    ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
    ipaddress.ip_network(
        "172.16.0.0/12"
    ),  # Docker bridge networks (for dev) (and includes 172.23.0.1 ie localnetwork)
    ipaddress.ip_network(
        "192.168.0.0/16"
    ),  # Docker compose networks (for the proxypi socket)
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
]


async def background_update(app):
    while True:
        await app.state.scraper.update()
        await asyncio.sleep(BACKGROUND_UPDATE_PERIOD)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scraper = Scraper()
    bg_task = asyncio.create_task(background_update(app))
    yield
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    await app.state.scraper.terminate()


app = FastAPI(
    title="Scraper",
    lifespan=lifespan,
)


@app.get("/check-ip", include_in_schema=False)
async def check_ip(request: Request):
    return await fast_api_ip_middleware.check_ip(request, ALLOWED_NETWORKS)


@app.middleware("http")
async def filter_ip_middleware(request: Request, call_next: Callable):
    return await fast_api_ip_middleware.filter_ip_middleware(
        request, call_next, ALLOWED_NETWORKS
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


@app.get("/health", include_in_schema=False)
async def health() -> Dict[str, Any]:
    """
    Health function for unit tests.
    Also useful to get the availability of the scraper.
    """
    try:
        return {
            "is_running_as_root": os.getuid() == 0,
            "can_create_browser": MAX_INSTANCES_PER_SCRAPER
            - len(app.state.scraper.browsers)
            > 0,
        }
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )


@app.get("/available")
async def available() -> Dict[str, bool]:
    try:
        return {
            "available": MAX_INSTANCES_PER_SCRAPER - len(app.state.scraper.browsers) > 0
        }
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )


@app.post("/new-instance", status_code=status.HTTP_201_CREATED)
async def new_instance(request: Optional[NewInstanceRequest] = NewInstanceRequest()):
    """
    Creates a new instances performing checks on its id
    and on the number of running instances.
    """
    if app.state.scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Browser instance with id {request.instance_id} already exists",
        )

    if len(app.state.scraper.browsers) > MAX_INSTANCES_PER_SCRAPER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Already too many opened instances {MAX_INSTANCES_PER_SCRAPER}",
        )

    try:
        await app.state.scraper.new_instance(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )


@app.post("/kill")
async def kill(request: KillRequest):
    """
    Kill the target instance correctly cleaning its tasks and processes.
    Does not return if the killing was successfull,
    as ending the chromedriver process may take some time.
    """
    if not app.state.scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No browser instance with id {request.instance_id}",
        )

    try:
        await app.state.scraper.kill(request.instance_id)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )


@app.get("/browsers")
async def browsers() -> Dict[str, Any]:
    """
    Returns as a JSON the information of the scraper and its running instances,
    including the entire browsing history of each instances that may be large.
    """
    try:
        return {
            instance_id: {
                "window_size": browser.window_size,
                "display": browser.display,
                "created_at": browser.created_at,
                "expires_at": browser.expires_at,
                "remaining_lifespan": browser.remaining_lifespan(),
                "status": browser.status(),
                "score": browser.score(),
                "browsing_history": browser.browsing_history,
            }
            for instance_id, browser in app.state.scraper.browsers.items()
        }
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )


@app.get("/stream/{instance_id}")
async def stream(instance_id: str):
    if not app.state.scraper.browser_exists(instance_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No browser instance with id {instance_id}",
        )

    try:
        return StreamingResponse(
            app.state.scraper.browsers[instance_id].stream(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"X-Accel-Buffering": "no"},
        )
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )


@app.post("/get")
async def get(request: GetRequest) -> str:
    """
    Core function to scrape a web page.
    Can support spam calls and execute the resquests sequentially,
    with no guarantee on the first one to resolve.
    """
    if not app.state.scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No browser instance with id {request.instance_id}",
        )

    if app.state.scraper.browsers[
        request.instance_id
    ].remaining_lifespan() < datetime.timedelta(seconds=LIFESPAN_BUFFER_GET_REQUEST):
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"The browser instance with id {request.instance_id} does not have sufficient lifespan",
        )

    try:
        return await app.state.scraper.get(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} at line {line}: {str(e)}",
        )
