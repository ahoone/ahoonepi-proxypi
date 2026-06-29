import asyncio
import datetime
import os
import sys
import traceback
from contextlib import asynccontextmanager

import httpx
from Config import Config
from core.Broker import Broker
from core.DatabaseHandler import DatabaseHandler
from core.NodeIdentifier import NodeIdentifier
from core.schemas import ClearRequest, CollectRequest, GetRequest, ScrapeRequest
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from starlette.background import BackgroundTask

sys.path.insert(0, "/plugins")
from middleware import add_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    await DatabaseHandler.initialize()
    app.state.broker = Broker()
    bg_task = asyncio.create_task(app.state.broker.background_update())

    yield

    bg_task.cancel()
    try:
        await bg_task
        await app.state.broker.terminate()
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Broker",
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
async def health():
    """
    Health function for unit tests.
    """
    return {
        "is_running_as_root": os.getuid() == 0,
        "broker_refresh_period": Config.REFRESH_PERIOD_BROKER,
        "broker_effective_refresh_period": app.state.broker.effective_refresh_period,
        "reachable_nodes": NodeIdentifier.reachable_nodes,
    }


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse("dashboard.html")


@app.get("/dashboard.css", include_in_schema=False)
async def css():
    return FileResponse("dashboard.css")


@app.post("/get")
async def get(request: GetRequest):
    """
    Gets an available browser from the broker,
    and shortcuts the request logic.
    Not designed to resist multiple calls,
    and maybe initialize multiple browsers at once,
    making it prone to detection.
    """
    try:
        browser = await app.state.broker.get_available_browser()
        if not browser:
            raise ValueError("no browser")
        else:
            print(browser.instance_id)
        return await browser.get(request.url)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.post("/scrape", status_code=status.HTTP_202_ACCEPTED)
async def scrape(request: ScrapeRequest):
    try:
        uuid = await app.state.broker.scrape(request)
        return {"uuid": uuid}
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/collect")
async def collect(request: CollectRequest):
    """
    returns just the successful request
    but should return a more complete object if:
    - the request is not done yet (anticipated time)
    - if all tries failed
    It also should mark the uuid as collected, and delete the entry
    """
    try:
        response = await app.state.broker.collect(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )
    if not response:
        raise HTTPException(
            status_code=425,
            detail=f"Still have not processed the target (or the id is wrong)",
        )
    return response


@app.get("/nodes")
async def nodes():
    try:
        return app.state.broker.to_dict()
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@app.get("/get_unscraped_targets")
async def get_unscraped_targets():
    try:
        return await app.state.broker.get_unscraped_targets()
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/results")
async def results():
    try:
        return await app.state.broker.get_scraped_targets()
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/logger")
async def logger():
    try:
        return app.state.broker.logger
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/stream/{hostname}/{instance_id}")
async def stream(hostname: str, instance_id: str):
    scraper = app.state.broker.get_scraper_from_hostname(hostname)
    if not scraper:
        raise HTTPException(
            status_code=409, detail=f"No scraper with hostname {hostname}"
        )

    if instance_id not in scraper.browsers.keys():
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance {instance_id} for scraper {hostname}",
        )

    url = f"http://{scraper.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/stream/{instance_id}"

    client = httpx.AsyncClient()
    req = client.build_request("GET", url)
    response = await client.send(req, stream=True)

    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        headers=dict(response.headers),
        background=BackgroundTask(client.aclose),
    )


@app.post("/clear")
async def clear(request: ClearRequest):
    """
    drops any running tasks and any running browser instance on all nodes
    Makes the broker hibernate (skip its update cycle)
    Will still load any task that was completed in the sqlite db
    """
    app.state.broker.clear(request)
