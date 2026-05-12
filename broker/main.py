
import asyncio
from contextlib import asynccontextmanager
import datetime
from fastapi import Body, FastAPI, status, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
    StreamingResponse,
)

import ipaddress
import json
import os

import random
import requests
from starlette.background import BackgroundTask
from string import Template, ascii_letters, digits
import subprocess
import sys
import traceback
from typing import Any, Callable, Dict, List, Literal, Union, Optional, Tuple, Set

from core.Broker import Broker
from core.Config import Config
from core.DatabaseHandler import DatabaseHandler
from core.NodeIdentifier import NodeIdentifier
from core.schemas import GetRequest, ScrapeRequest

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    # ipaddress.ip_network("10.0.0.0/24"),      # VPN network
    ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
    ipaddress.ip_network("172.16.0.0/12"),  # Docker bridge networks (for dev)
    ipaddress.ip_network(
        "192.168.0.0/16"
    ),  # Docker compose networks (for the proxypi socket)
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    await DatabaseHandler.initialize()
    app.state.broker = Broker()
    bg_task = asyncio.create_task(app.state.broker.background_update())

    yield

    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Broker",
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
        await app.state.broker.scrape(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/nodes")
async def nodes():
    try:
        return app.state.broker.to_dict()
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/broker")
async def broker():
    try:
        return await app.state.broker.get_scraping_list()
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
