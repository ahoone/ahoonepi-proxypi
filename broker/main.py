import asyncio
from contextlib import asynccontextmanager
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import ipaddress
import os
from pydantic import HttpUrl
import random
import sqlite3
import sys
from typing import Any, Callable, Dict, List, Literal, Union 

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware
import proxypi

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "LIGHTHOUSE" in NODE_ROLE, "The node should be a lighthouse (ie includes broker) to launch this image"


BROKER_DATABASE="broker.db"
BROKER_CLEAR_DB_ON_STARTUP=True

DB_TABLE_URIS_TARGETS="uris_targets"
DB_TABLE_URIS_RESPONSES="uris_responses"


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class TabImage:

    def __init__(self) -> None:
        self.id: int = None
        self.uri: str = None
        self.status: Literal["idle", "requesting"] = None


class BrowserInstanceImage:

    def __init__(self) -> None:
        self.id: int = None
        self.start_timestamp: datetime.datetime = None
        self.end_timestamp: datetime.datetime = None
        self.status: Literal["idle", "requesting"] = None
        self.camera = None
        self.browsing_history: List[str] = []
        self.tabs: List[TabImage] = []


class ScraperImage:

    def __init__(self, vpn_address: str) -> None:
        self.online: bool = True
        self.vpn_address: str = vpn_address
        self.hostname: str = None
        self.port: str = None
        self.ipv6: str = None
        self.ssh_latency: int = None
        self.internet_latency: int = None
        self.vpn_latency: int = None
        self.spotted: bool = None
        self.browser_instances: List[BrowserInstanceImage] = []


class Broker:

    def __init__(
        self,
    ) -> None:
        self.scrapers: List[ScraperImage] = []
        self.db_con = None


    # __INIT__ CAN NOT BE ASYNC IN PYTHON
    @classmethod
    async def create(cls) -> "Broker":
        broker = cls()
        await broker.__initialize()
        return broker


    async def __initialize(self) -> None:
        await self.update()
        self.db_con = sqlite3.connect(BROKER_DATABASE)
        self.db_cur = self.db_con.cursor()
        self.initialize_db_tables()


    def initialize_db_tables(self) -> None:
        response = self.db_cur.execute("SELECT name FROM sqlite_master")
        if response and DB_TABLE_URIS_TARGETS not in response.fetchall():
            self.db_cur.execute(f"CREATE TABLE {DB_TABLE_URIS_TARGETS}(uris, timestamp)")
        if response and DB_TABLE_URIS_RESPONSES not in response.fetchall():
            self.db_cur.execute(f"CREATE TABLE {DB_TABLE_URIS_RESPONSES}(uris, response, request_timestamp, response_timestamp)")


    def promise_scrape(self, uris: Union[str, List[str]]) -> None:
        data = [(uris, datetime.datetime.now())] if isinstance(uris, str) else [(uri, datetime.datetime.now()) for uri in uris]
        query = f"INSERT INTO {DB_TABLE_URIS_TARGETS} VALUES (?, ?)"
        self.db_cur.executemany(query, data)
        self.db_con.commit()


    def get_table_uris_targets(self) -> List[Dict[str, Any]]:
        query = f"SELECT * FROM {DB_TABLE_URIS_TARGETS}"
        self.db_cur.execute(query)
        columns = [desc[0] for desc in self.db_cur.description]
        return [dict(zip(columns, row)) for row in self.db_cur.fetchall()]


    async def update(self) -> None:

        vpn_addresses_availables = (await proxypi.run("ping-wireguard -a")).splitlines()

        for vpn_address in vpn_addresses_availables:
            if vpn_address not in [_.vpn_address for _ in self.scrapers]:
                self.scrapers.append(ScraperImage(vpn_address))

        for scraper in self.scrapers:
            if scraper.vpn_address not in vpn_addresses_availables:
                scraper.online = False


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
    if BROKER_CLEAR_DB_ON_STARTUP and os.path.exists(BROKER_DATABASE):
        os.remove(BROKER_DATABASE)
        # automatically created by sqlite3.connect(BROKER_DATABASE)
    app.state.broker = await Broker.create()
    yield
    sqlite3.close(app.state.broker.db_con)


app = FastAPI(
    title="Broker API",
    description="Broker",
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


@app.get("/")
async def home():
    return FileResponse("dashboard.html")

@app.get("/dashboard.css")
async def css():
    return FileResponse("dashboard.css")



@app.post("/scrape/")
async def promise_scrape(uris: Union[str, List[str]]):
# async def promise_scrape(uris: Union[HttpUrl, List[HttpUrl]]):
    try:
        app.state.broker.promise_scrape(uris)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/table-uris-targets")
async def get_table_uris_targets():
    try:
        return app.state.broker.get_table_uris_targets()
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/wireguard-status")
async def wireguard_status():
    try:
        return [_.__dict__ for _ in app.state.broker.scrapers]
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


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
