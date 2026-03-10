import asyncio
from contextlib import asynccontextmanager
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import ipaddress
import os
import random
import sqlite3
import sys
from typing import List, Dict, Callable

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware
import proxypi

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "LIGHTHOUSE" in NODE_ROLE, "The node should be a lighthouse (ie includes broker) to launch this image"


BROKER_DATABASE="broker.db"
BROKER_CLEAR_DB_ON_STARTUP=True


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class Broker:

    def __init__(
        self,
    ) -> None:
        self._initialized: bool = False
        self.scrapers: List[str] = []
        self.db_con = None

    # __INIT__ CAN NOT BE ASYNC IN PYTHON
    @classmethod
    async def create(cls) -> "Broker":
        broker = cls()
        await broker.initialize()
        return broker

    async def initialize(self) -> None:
        if not self._initialized:
            await self.update_scrapers()
            self.db_con = sqlite3.connect(BROKER_DATABASE)
            self.db_cur = self.db_con.cursor()
            self._initialized = True


    async def update_scrapers(self) -> None:
        # take a look at /proxypi.sh wireguard::ping
        self.scrapers = (await proxypi.run("ping-wireguard -a")).splitlines()



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
    if BROKER_CLEAR_DB_ON_STARTUP:
        os.remove(BROKER_DATABASE)
    app.state.broker = await Broker.create()
    yield
    sqlite3.close(app.state.broker.db_con)


app = FastAPI(
    title="Broker API",
    description="Scraper",
    version="1.0.0",
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


@app.get("/wireguard-status")
async def wireguard_status():
    try:
        return {"output": app.state.broker.scrapers}
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/")
async def home():
    return FileResponse("dashboard.html")

@app.get("/dashboard.css")
async def css():
    return FileResponse("dashboard.css")


@app.get("/nodes")
async def nodes():
    try:
        result = await proxypi.run("ping")
        return {"output": result.splitlines()}
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )
