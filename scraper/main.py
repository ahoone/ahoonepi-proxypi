import asyncio
import datetime
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from Config import Config
from core.schemas import GetRequest, KillRequest, NewInstanceRequest
from core.Scraper import Scraper
from fastapi import FastAPI, HTTPException, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

sys.path.insert(0, "/plugins")
from middleware import add_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


LIFESPAN_BUFFER_GET_REQUEST = 5  # seconds


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scraper = Scraper()
    bg_task = asyncio.create_task(app.state.scraper.background_update())
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

add_middleware(app, Config.ALLOWED_NETWORKS)

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
        ram_total, ram_used, ram_free = map(
            int, os.popen("free -b").readlines()[1].split()[1:4]
        )

        return {
            "is_running_as_root": os.getuid() == 0,
            "can_create_browser": len(app.state.scraper.browsers)
            < Config.MAX_INSTANCES_PER_SCRAPER,
            "ram_specs": f"{ram_total // 1024**3}GiB",
            "ram_usage": f"{(100 * ram_used) // ram_total}%",
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
            "available": len(app.state.scraper.browsers)
            < Config.MAX_INSTANCES_PER_SCRAPER,
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

    if len(app.state.scraper.browsers) > Config.MAX_INSTANCES_PER_SCRAPER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Already too many opened instances {Config.MAX_INSTANCES_PER_SCRAPER}",
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
