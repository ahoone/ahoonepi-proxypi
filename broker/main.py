import asyncio
import os
import sys
import traceback
from contextlib import asynccontextmanager
from typing import List

import httpx
from Config import Config
from core.Broker import Broker
from core.DatabaseHandler import DatabaseHandler, RecordUnscrapedTarget
from core.NodeIdentifier import NodeIdentifier
from core.schemas import (
    ClearRequest,
    CollectRequest,
    CollectRequestResponse,
    ScrapeRequest,
    ScrapeRequestResponse,
)
from core.ScraperImage import ScraperImageModel
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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


@app.post(
    "/scrape",
    description=(
        "Main method of getting the broker to scrape an url. "
        "The request will be loaded in the database and the broker will plan it. "
        "This endpoint should be used with `get.collect`. "
        "One improvment would be to add an expected time of collect. "
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
async def scrape(request: ScrapeRequest) -> ScrapeRequestResponse:
    try:
        return await app.state.broker.scrape(request)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@app.get(
    "/collect",
    description=(
        "Returns the successful html content associated with the url. "
        "May return different codes depending on the status of the requests. "
    ),
)
async def collect(request: CollectRequest) -> CollectRequestResponse:
    query = f"""
        SELECT 1
        FROM {Config.DB_TABLE_TARGETS}
        WHERE id = (?)
    """
    try:
        response = await DatabaseHandler.fetchone(query, (str(request.uuid),))
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
    if not response:
        raise HTTPException(
            status_code=404,
            detail=f"Given UUID {request.uuid} is not known as a target.",
        )

    try:
        response = await app.state.broker.get_running_tasks()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
    if request.uuid in response:
        raise HTTPException(
            status_code=425,
            detail="Processing the target.",
        )

    query = query = f"""
        SELECT *
        FROM {Config.DB_TABLE_REQUESTS}
        WHERE 1=1
            AND success = TRUE
            AND {Config.DB_TABLE_TARGETS}_id = '{request.uuid}'
        ORDER BY id ASC
    """
    try:
        response = await DatabaseHandler.fetchone(query)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
    if not response:
        raise HTTPException(
            status_code=425,
            detail="Target yet to be proceed.",
        )
    return CollectRequestResponse(content=response["content"])


@app.get(
    "/nodes",
    description=(
        "Displays information about the nodes and their scraper component. "
        "Endpoint used by the dashboard. "
    ),
)
async def nodes() -> List[ScraperImageModel]:
    try:
        return app.state.broker.to_dict()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@app.get("/get_unscraped_targets")
async def get_unscraped_targets() -> List[RecordUnscrapedTarget]:
    try:
        return await DatabaseHandler.get_unscraped_targets()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@app.get("/results")
async def results():
    try:
        return await DatabaseHandler.get_scraped_targets()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@app.get("/logger")
async def logger():
    try:
        return app.state.broker.logger
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())


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


@app.post(
    "/clear",
    description=(
        "Implements different flags to clear states handled by the broker without restarting the service. "
        "Makes the broker hibernate (skip its update cycle) until completed. "
        "An improvement would be to cancel tasks with a specified `tag`. "
    ),
)
async def clear(request: ClearRequest):
    try:
        await app.state.broker.clear(request)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
