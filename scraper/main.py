import asyncio
from contextlib import asynccontextmanager
import datetime
from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
import ipaddress
import nodriver as uc
import os
from pydantic import BaseModel
import random
import subprocess
import sys
import threading
from typing import Tuple, List, Dict, Callable, Optional, Union, BinaryIO, Any


sys.path.insert(0, "/plugins")
import fast_api_ip_middleware


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "SCRAPER" in NODE_ROLE, "The node should be a scraper to launch this image"


DISPLAY_DEPTH=24
DISPLAY_CLOSE_TIMEOUT=6
BROWSER_DEFAULT_ID="default"
BROWSER_DEFAULT_LIFESPAN=3600  # 1 hour in seconds
BROWSER_DEFAULT_WINDOW=[1920, 1080]
STREAM_QUALITY=15  # 2=best 31=worst
STREAM_FPS=12
STREAM_CLOSE_TIMEOUT=6
STREAM_CHUNK_SIZE=16384
JPEG_MARKER_START=b"\xFF\xD8\xFF"
JPEG_MARKER_END=b"\xFF\xD9"
FRAME_UNPACKING_SUBPROCESS_TIMEOUT=3


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


# class Profile:
# Should be sent by the Broker
#     def __init__(self) -> None:
#         self.mouse_movements = None
#         self.scrolling_speed = None


class Browser:

    display = 100  # First Xvfb (instead of 99)

    def __init__(self) -> None:
        self.window_size: Tuple[int, int] = None
        self.display = None
        self.__display_process = None
        self.__driver = None
        self.__streaming_process = None
        self.created_at = None
        self.expires_at = None
        self.browsing_history: List[Dict] = []


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


    async def __create_driver(self):
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


    def __close_display(self) -> None:
        # This version does not account for Xvfb creating its own child processes
        if not self.__display_process:
            return

        self.__display_process.terminate()
        try:
            self.__display_process.wait(timeout=DISPLAY_CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.__display_process.kill()


    async def __initialize(
        self,
        lifespan_in_seconds: int,
        window_size: Tuple[int, int],
    ) -> None:
        self.window_size = window_size
        self.__create_display()
        self.__driver = await self.__create_driver()
        self.created_at = datetime.datetime.now()
        self.expires_at = self.created_at + datetime.timedelta(seconds=lifespan_in_seconds)


    def kill(self) -> None:
        self.__kill_streaming_process()
        self.__close_display()
        self.__driver.stop()


    def __create_streaming_process(self) -> None:

        if self.__streaming_process:
            return

        command = [
            "ffmpeg",
            "-loglevel", "quiet",
            "-f", "x11grab",
            "-framerate", str(STREAM_FPS),
            "-video_size", f"{self.window_size[0]}x{self.window_size[1]}",
            "-i", self.display,
            "-f", "mjpeg",
            "-q:v", str(STREAM_QUALITY),
            "-flush_packets", "1",
            "pipe:1",
        ]

        self.__streaming_process = subprocess.Popen(
            command,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            env = {**os.environ, "DISPLAY": self.display},
        )


    def __kill_streaming_process(self) -> None:
        if not self.__streaming_process:
            return

        self.__streaming_process.terminate()
        try:
            self.__streaming_process.wait(timeout=STREAM_CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.__streaming_process.kill()


    @staticmethod
    def __unpack_frames(stream: BinaryIO) -> bytes:
        buffer = b""
        while chunk := stream.read(STREAM_CHUNK_SIZE):
            buffer += chunk
            while True:
                pos_start = buffer.find(JPEG_MARKER_START)
                pos_end = buffer.find(JPEG_MARKER_END)
                if pos_start == -1 or pos_end == -1:
                    break
                yield buffer[pos_start:pos_end + len(JPEG_MARKER_END)]
                buffer = buffer[pos_end + len(JPEG_MARKER_END):]


    async def stream(self) -> bytes:
        if not self.__streaming_process:
            self.__create_streaming_process()
        # The streaming subprocess only stops when the instance expires

        latest_frame = None
        loop = asyncio.get_event_loop()
        new_frame_event = asyncio.Event()
        stop_event = asyncio.Event()

        def __unpack_through_thread() -> None:
            nonlocal latest_frame
            for frame in self.__unpack_frames(self.__streaming_process.stdout):
                latest_frame = frame
                loop.call_soon_threadsafe(new_frame_event.set)

        thread = threading.Thread(
            target = __unpack_through_thread,
            daemon = True,
        )
        thread.start()

        try:
            while True:
                await new_frame_event.wait()
                new_frame_event.clear()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + latest_frame +
                    b"\r\n"
                )
        finally:
            # self.__kill_streaming_process()
            stop_event.set()
            await asyncio.to_thread(thread.join, timeout=FRAME_UNPACKING_SUBPROCESS_TIMEOUT)


    async def get(self, uri: str) -> str:
        access_record = {
            "uri": uri,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "in_progress",
        }

        try:
            page = await self.__driver.get(uri)
            html_content = await page.get_content()

            access_record["status"] = "success"
            access_record["content_length"] = len(html_content)
            access_record["completed_at"] = datetime.datetime.now().isoformat()

            self.browsing_history.append(access_record)
            return html_content

        except Exception as e:
            access_record["status"] = "failed"
            access_record["error"] = str(e)
            access_record["completed_at"] = datetime.datetime.now().isoformat()

            self.browsing_history.append(access_record)
            raise


class NewInstanceRequest(BaseModel):
    instance_id: str = BROWSER_DEFAULT_ID
    lifespan_in_seconds: int = BROWSER_DEFAULT_LIFESPAN
    window_size: Union[List[int], Tuple[int, int]] = BROWSER_DEFAULT_WINDOW


class KillRequest(BaseModel):
    instance_id: str


class GetRequest(BaseModel):
    instance_id: str
    uri: str


class Scraper:

    def __init__(self) -> None:
        self.browsers: Dict[str, Browser] = {}

    def browser_exists(self, instance_id: str) -> bool:
        return instance_id in self.browsers.keys()

    async def new_instance(self, request: Optional[NewInstanceRequest]) -> None:
        self.browsers[request.instance_id] = await Browser.create(request.lifespan_in_seconds, request.window_size)

    def kill(self, instance_id: str) -> None:
        self.browsers[instance_id].kill()
        del self.browsers[instance_id]

    async def get(self, request: GetRequest) -> Dict[Any, Any]:
        browser = self.browsers[request.instance_id]
        return await browser.get(request.uri)

    def terminate(self) -> None:
        [_.kill() for _ in self.browsers.values()]

    def update(self) -> None:
        # we must not iterate over the dictionary while editing it
        expired = [instance_id for instance_id, browser in self.browsers.items() if datetime.datetime.now() >= browser.expires_at]
        for instance_id in expired:
            self.kill(instance_id)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),     # localhost
    # ipaddress.ip_network("10.0.0.0/24"),   # VPN network
    ipaddress.ip_network("10.0.0.1/32"),     # Lighthouse through VPN
    ipaddress.ip_network("172.16.0.0/12"),   # Docker bridge networks (for dev) (and includes 172.23.0.1 ie localnetwork)
    ipaddress.ip_network("192.168.0.0/16"),  # Docker compose networks (for the proxypi socket)
    ipaddress.ip_network("::1/128"),         # IPv6 localhost
]


async def background_update(app):
    loop = asyncio.get_running_loop()
    while True:
        await loop.run_in_executor(None, app.state.scraper.update)
        await asyncio.sleep(1)


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
    app.state.scraper.terminate()


app = FastAPI(
    title="Scraper",
    lifespan=lifespan,
)


@app.get("/check-ip")
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


@app.post("/new_instance")
async def new_instance(request: Optional[NewInstanceRequest] = NewInstanceRequest()):
    if app.state.scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409, detail=f"Browser instance with id {request.instance_id} already exists"
        )

    try:
        await app.state.scraper.new_instance(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.post("/kill")
async def kill(request: KillRequest):
    if not app.state.scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409, detail=f"No browser instance with id {request.instance_id}"
        )

    try:
        app.state.scraper.kill(request.instance_id)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/browsers")
async def browsers():
    try:
        return {
            instance_id: {
                "window_size": browser.window_size,
                "display": browser.display,
                "created_at": browser.created_at,
                "expires_at": browser.expires_at,
                "remaining_lifespan": browser.expires_at - datetime.datetime.now(),
                "browsing_history": browser.browsing_history,  # maybe we'll not always want this, response may be too large
            } for instance_id, browser in app.state.scraper.browsers.items()
        }
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/stream/{instance_id}")
async def stream(instance_id: str):
    if not app.state.scraper.browser_exists(instance_id):
        raise HTTPException(
            status_code=409, detail=f"No browser instance with id {instance_id}"
        )

    try:
        return StreamingResponse( 
            app.state.scraper.browsers[instance_id].stream(),
            media_type = "multipart/x-mixed-replace; boundary=frame",
            headers={"X-Accel-Buffering": "no"},
        )
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.post("/get")
async def get(request: GetRequest):
    if not app.state.scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409, detail=f"No browser instance with id {request.instance_id}"
        )

    try:
        return await app.state.scraper.get(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )

