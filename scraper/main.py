import asyncio
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


LIFESPAN_BROWSER = 1  # in hours
PAGE_LOADING_UNIFORM_RANGE = (2, 4)  # in seconds
PAGE_SCROLLING_UNIFORM_RANGE = (200, 400)  # 100 <=> height of the browser window
PERIOD_CLEANUP_LOOP = 300  # in seconds


STREAM_DISPLAY = ":99"
STREAM_WIDTH = 1920
STREAM_HEIGHT = 1080


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


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    # ipaddress.ip_network("10.0.0.0/24"),      # VPN network
    ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
    ipaddress.ip_network("172.16.0.0/12"),    # Docker bridge networks (for dev) (and includes 172.23.0.1 ie localnetwork)
    ipaddress.ip_network(
        "192.168.0.0/16"
    ),  # Docker compose networks (for the proxypi socket)
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
]


app = FastAPI(title="Scraper API", description="Scraper", version="1.0.0")


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
        self.access_history: List[Dict] = []


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

        latest_frame = None
        loop = asyncio.get_event_loop()
        new_frame_event = asyncio.Event()

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
            thread.join()


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

            self.access_history.append(access_record)
            return html_content

        except Exception as e:
            access_record["status"] = "failed"
            access_record["error"] = str(e)
            access_record["completed_at"] = datetime.datetime.now().isoformat()

            self.access_history.append(access_record)
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
        return instance_id in scraper.browsers.keys()

    async def new_instance(self, request: Optional[NewInstanceRequest]) -> None:
        self.browsers[request.instance_id] = await Browser.create(request.lifespan_in_seconds, request.window_size)

    def kill(self, instance_id: str) -> None:
        self.browsers[instance_id].kill()
        del self.browsers[instance_id]

    async def get(self, request: GetRequest) -> Dict[Any, Any]:
        browser = self.browsers[request.instance_id]
        return await browser.get(request.uri)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


scraper = Scraper()


@app.post("/new_instance")
async def new_instance(request: Optional[NewInstanceRequest] = NewInstanceRequest()):
    if scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409, detail=f"Browser instance with id {request.instance_id} already exists"
        )

    try:
        await scraper.new_instance(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.post("/kill")
async def kill(request: KillRequest):
    if not scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409, detail=f"No browser instance with id {request.instance_id}"
        )

    try:
        scraper.kill(request.instance_id)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/browsers")
async def browsers():
    try:
        return [
            {instance_id: {
                "window_size": browser.window_size,
                "display": browser.display,
                "created_at": browser.created_at,
                "expires_at": browser.expires_at,
                "access_history": browser.access_history,
            }}
            for instance_id, browser in scraper.browsers.items()
        ]
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/stream/{instance_id}")
async def stream(instance_id: str):
    if not scraper.browser_exists(instance_id):
        raise HTTPException(
            status_code=409, detail=f"No browser instance with id {instance_id}"
        )

    try:
        return StreamingResponse( 
            scraper.browsers[instance_id].stream(),
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
    if not scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409, detail=f"No browser instance with id {request.instance_id}"
        )

    try:
        return await scraper.get(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


























class BrowserInstance:

    def __init__(
        self,
        expiration_date: datetime.datetime = None,
    ) -> None:
        self.browser = None
        self.expiration_date = None
        self._initialized = False
        self.created_at = datetime.datetime.now()
        self.access_history: List[Dict] = []

    # __INIT__ CAN NOT BE ASYNC IN PYTHON
    async def initialize(self, expiration_date: datetime.datetime = None):
        """Initialize the browser (called once)"""
        self.expiration_date = expiration_date or (
            datetime.datetime.now() + datetime.timedelta(hours=LIFESPAN_BROWSER)
        )
        if not self._initialized:
            self.browser = await uc.start(
                headless=False,  # If headerless, Cloudflare spots us.
                browser_args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1920,1080",
                    "--window-position=0,0",
                ],  # If images are blocked, Cloudflare spots us.
                sandbox=False,
            )
            self._initialized = True
        return self

    async def scrape(self, url: str) -> str:
        """Scrape a URL using the persistent browser"""
        if not self._initialized:
            await self.initialize()

        access_record = {
            "url": url,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "in_progress",
        }

        try:
            page = await self.browser.get(url)
            await page.sleep(random.uniform(*PAGE_LOADING_UNIFORM_RANGE))

            SCROLL_JUMP = 20
            for _ in range(random.randint(*PAGE_SCROLLING_UNIFORM_RANGE)):
                if _ % SCROLL_JUMP == 0:
                    await page.scroll_down(SCROLL_JUMP)
            await page.scroll_down(SCROLL_JUMP)


            html_content = await page.get_content()

            access_record["status"] = "success"
            access_record["content_length"] = len(html_content)
            access_record["completed_at"] = datetime.datetime.now().isoformat()

            self.access_history.append(access_record)
            return html_content

        except Exception as e:
            access_record["status"] = "failed"
            access_record["error"] = str(e)
            access_record["completed_at"] = datetime.datetime.now().isoformat()
            self.access_history.append(access_record)
            raise

    def close(self):
        """Explicitly close the browser"""
        if self.browser:
            self.browser.stop()
            self._initialized = False

    def is_expired(self) -> bool:
        """Check if this instance has expired"""
        return datetime.datetime.now() > self.expiration_date

    def get_stats(self) -> Dict:
        """Get statistics about this instance"""
        total_requests = len(self.access_history)
        successful_requests = sum(
            1 for record in self.access_history if record["status"] == "success"
        )
        failed_requests = sum(
            1 for record in self.access_history if record["status"] == "failed"
        )

        return {
            "created_at": self.created_at.isoformat(),
            "expiration_date": self.expiration_date.isoformat(),
            "is_expired": self.is_expired(),
            "is_initialized": self._initialized,
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "access_history": self.access_history,
        }

    def _capture_frame(self) -> bytes | None:
        """
        Capture a single JPEG frame from the Xvfb display using ffmpeg x11grab.
        Runs synchronously — called via asyncio.to_thread to avoid blocking.
        Returns raw JPEG bytes, or None on failure.
        """
        command = [
            "ffmpeg",
            "-loglevel", "quiet",        # Suppress ffmpeg output
            "-f", "x11grab",             # X11 screen capture input
            "-framerate", str(STREAM_FPS),
            "-video_size", f"{STREAM_WIDTH}x{STREAM_HEIGHT}",
            "-i", STREAM_DISPLAY,        # Xvfb display
            "-vframes", "1",             # Capture exactly one frame
            "-f", "image2",
            "-vcodec", "mjpeg",
            "-q:v", "5",                 # JPEG quality (2=best, 31=worst)
            "pipe:1",                    # Output to stdout
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=2,               # Fail fast if ffmpeg hangs
                env={**os.environ, "DISPLAY": STREAM_DISPLAY},
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return

    async def stream_screen(self, fps: int = STREAM_FPS):
        """
        Async generator that yields MJPEG multipart frames for FastAPI StreamingResponse.

        Usage in FastAPI:
            StreamingResponse(
                instance.stream_screen(),
                media_type="multipart/x-mixed-replace; boundary=frame"
            )
        """
        frame_interval = 1.0 / fps
        while True:
            frame_start = asyncio.get_event_loop().time()
            jpeg_bytes = await asyncio.to_thread(self._capture_frame)

            if jpeg_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"\r\n" + jpeg_bytes + b"\r\n"
                )

            elapsed = asyncio.get_event_loop().time() - frame_start
            sleep_time = max(0.0, frame_interval - elapsed)
            await asyncio.sleep(sleep_time)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class BrowserInstancePool:

    def __init__(self):
        self.instances: dict[str, BrowserInstance] = {}

    async def get_or_create_instance(self, instance_id: str) -> BrowserInstance:
        """Get existing instance or create new one"""
        if instance_id not in self.instances:
            instance = BrowserInstance()
            await instance.initialize()
            self.instances[instance_id] = instance

        instance = self.instances[instance_id]

        if instance.is_expired():
            instance.close()
            instance = BrowserInstance()
            await instance.initialize()
            self.instances[instance_id] = instance

        return instance

    def cleanup_expired(self):
        """Remove and close expired instances"""
        expired_ids = [
            instance_id
            for instance_id, instance in self.instances.items()
            if instance.is_expired()
        ]
        for instance_id in expired_ids:
            self.instances[instance_id].close()
            del self.instances[instance_id]

    def get_all_stats(self) -> Dict:
        """Get stats for all instances"""
        return {
            instance_id: instance.get_stats()
            for instance_id, instance in self.instances.items()
        }


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


pool = BrowserInstancePool()


@app.post("/scrape")
async def scrape_endpoint(url: str, instance_id: str = "default"):
    """Scrape a URL using a persistent browser instance"""
    try:
        instance = await pool.get_or_create_instance(instance_id)
        content = await instance.scrape(url)
        return {
            "status": "success",
            "content": content,
            "instance_id": instance_id,
        }
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


# @app.post("/close-instance")
# def close_instance(instance_id: str):
#     """Manually close a browser instance"""
#     try:
#         if instance_id in pool.instances:
#             stats = pool.instances[instance_id].get_stats()
#             pool.instances[instance_id].close()
#             del pool.instances[instance_id]
#             return {
#                 "status": "closed",
#                 "instance_id": instance_id,
#                 "final_stats": stats,
#             }
#         return {"status": "not_found", "instance_id": instance_id}
#     except Exception as e:
#         line = sys.exc_info()[2].tb_lineno
#         raise HTTPException(
#             status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
#         )


@app.get("/instances")
async def list_instances():
    """List all active instances with their access history"""
    return {
        "total_instances": len(pool.instances),
        "instances": pool.get_all_stats(),
    }


@app.get("/instance/{instance_id}")
async def get_instance_details(instance_id: str):
    """Get detailed information about a specific instance"""
    if instance_id not in pool.instances:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    return {
        "instance_id": instance_id,
        **pool.instances[instance_id].get_stats(),
    }


@app.get("/instance/{instance_id}/history")
async def get_instance_history(instance_id: str):
    """Get access history for a specific instance"""
    if instance_id not in pool.instances:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    return {
        "instance_id": instance_id,
        "access_history": pool.instances[instance_id].access_history,
    }


@app.get("/stats")
async def get_global_stats():
    """Get global statistics across all instances"""
    all_stats = pool.get_all_stats()

    total_requests = sum(stats["total_requests"] for stats in all_stats.values())
    total_successful = sum(stats["successful_requests"] for stats in all_stats.values())
    total_failed = sum(stats["failed_requests"] for stats in all_stats.values())

    return {
        "total_instances": len(pool.instances),
        "total_requests": total_requests,
        "successful_requests": total_successful,
        "failed_requests": total_failed,
        "instances": all_stats,
    }


@app.get("/browser/{instance_id}/stream")
async def stream_browser_screen(instance_id: str, fps: int = STREAM_FPS):
    """
    Stream the live browser screen as an MJPEG stream.
    Renderable directly in a browser <img> tag or via VLC/ffplay.
    """
    instance = pool.instances[instance_id]

    fps = max(1, min(fps, 24))

    return StreamingResponse(
        instance.stream_screen(fps=fps),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            # Prevent proxies/CDNs from buffering the stream
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering if behind Nginx
        },
    )


@app.get("/stream/{instance_id}", response_class=HTMLResponse)
async def stream_browser_viewer(instance_id: str):
    """
    Convenience endpoint: a minimal HTML page to view the stream in a browser tab.
    Navigate to /browser/{id}/stream/viewer to watch live.
    """
    return f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Browser Stream — {instance_id}</title>
        <style>
          body {{ margin: 0; background: #111; display: flex; justify-content: center; align-items: center; height: 100vh; }}
          img {{ max-width: 100%; max-height: 100vh; }}
        </style>
      </head>
      <body>
        <img src="/browser/{instance_id}/stream" alt="Live browser stream" />
      </body>
    </html>
    """


# @app.on_event("startup")
# async def startup_event():
#     """Cleanup expired instances regularly"""

#     async def cleanup_loop():
#         while True:
#             await asyncio.sleep(PERIOD_CLEANUP_LOOP)
#             await pool.cleanup_expired()

#     asyncio.create_task(cleanup_loop())
