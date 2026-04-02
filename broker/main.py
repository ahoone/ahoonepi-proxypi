import asyncio
from contextlib import asynccontextmanager
import datetime
from fastapi import Body, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
import httpx
import ipaddress
import json
import os
from pydantic import HttpUrl, BaseModel
import random
import requests
import sqlite3  # native // does not need to be in requirements.txt
from starlette.background import BackgroundTask
from string import Template
import sys
from typing import Any, Callable, Dict, List, Literal, Union 

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware
import proxypi

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "LIGHTHOUSE" in NODE_ROLE, "The node should be a lighthouse (ie includes broker) to launch this image"


BROKER_DATABASE = "broker.db"
BROKER_CLEAR_DB_ON_STARTUP = True

DB_TABLE_URIS_TARGETS = "uris_targets"
DB_TABLE_URIS_RESPONSES = "uris_responses"

PROXYPI_COMMAND_INFO = Template("info $node_id")
PROXYPI_COMMAND_AVAILABLE_NODES = "ping-wireguard -a"
PROXYPI_COMMAND_RAM = Template("ram $node_id")

DISPLAY_LIMIT_SCRAPING_LIST = 200


HTTP_PORT_SCRAPER = os.getenv("HTTP_PORT_SCRAPER")

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


# class TabImage:

#     def __init__(self) -> None:
#         self.id: int = None
#         self.uri: str = None
#         self.status: Literal["idle", "requesting"] = None


class BrowserImage:

    def __init__(self, scraper_response: Dict[str, Any]) -> None:
        self.created_at: datetime.datetime = scraper_response["created_at"]
        self.expires_at: datetime.datetime = scraper_response["expires_at"]
        self.browsing_history: List[str] = []
        self.status: Literal["idle", "requesting", "spotted"] = scraper_response["status"]
        # self.tabs: List[TabImage] = []


class ScraperImage:

    def __init__(self) -> None:
        self.online: bool = None
        self.vpn_address: str = None  # UNIQUE (primary key)
        self.node_id: int = None  # UNIQUE (equivalent to primary key)
        self.hostname: str = None  # UNIQUE
        self.port: str = None  # UNIQUE (equivalent to primary key)
        self.ipv6: str = None
        self.ram_specs: str = None
        self.ram_usage: str = None
        # self.electricity_consumption: ?
        # self.ssh_latency: int = None
        # self.internet_latency: int = None
        # self.vpn_latency: int = None
        # self.spotted: bool = None
        self.browsers: Dict[str, BrowserImage] = {}  # instance_id: browser


    # __INIT__ CAN NOT BE ASYNC
    @classmethod
    async def create(cls, vpn_address: str) -> "ScraperImage":
        scraperImage = cls()
        await scraperImage.__initialize(vpn_address)
        return scraperImage


    async def __initialize(self, vpn_address: str) -> None:
        self.online = True
        self.vpn_address = vpn_address
        self.node_id = int(vpn_address.split(".")[-1])
        response = await proxypi.run(PROXYPI_COMMAND_INFO.safe_substitute(node_id=self.node_id))
        self.__dict__.update(json.loads(response))
        # The update of the ipv6 is not raised by the proxy (ie need to refresh manually)


    async def update(self) -> None:
        ram_response = await proxypi.run(PROXYPI_COMMAND_RAM.safe_substitute(node_id=self.node_id))
        data = json.loads(ram_response)
        self.ram_specs = data['ram_specs']
        self.ram_usage = data['ram_usage']

        self.browsers = {}
        scraper_response = requests.get(f"http://{self.vpn_address}:{HTTP_PORT_SCRAPER}/browsers")
        scraper_response_as_dict = json.loads(scraper_response.text)
        if not scraper_response.ok:
            return
        for instance_id, browser_as_dict in scraper_response_as_dict.items():
            print(browser_as_dict)
            self.browsers[instance_id] = BrowserImage(browser_as_dict)

        # dropping outdated/killed instances
        # emptying self.browsers may be too memory intensive because of the browsing history
        # but the BrowserImage just on top is always reloading everything...
        # for instance_id in self.browsers:
        #     if instance_id not in scraper_response_as_dict:
        #         del self.browsers[instance_id]

        # self.browsers.update()


class Broker:

    def __init__(
        self,
    ) -> None:
        self.scrapers: Dict[str, ScraperImage] = {}  # vpn_address -> scraper
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
            self.db_cur.execute(f"""
                CREATE TABLE {DB_TABLE_URIS_TARGETS} (
                    id INTEGER PRIMARY KEY,
                    uri TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tag TEXT
                );
            """)
        if response and DB_TABLE_URIS_RESPONSES not in response.fetchall():
            self.db_cur.execute(f"""
                CREATE TABLE {DB_TABLE_URIS_RESPONSES} (
                    uri,
                    response,
                    request_timestamp,
                    response_timestamp
                );
            """)


    def promise_scrape(self, uris: Union[str, List[str]], tag: str = None) -> None:
        data = [(uris, tag)] if isinstance(uris, str) else [(uri, tag) for uri in uris]
        query = f"INSERT INTO {DB_TABLE_URIS_TARGETS} (uri, tag) VALUES (?, ?)"
        self.db_cur.executemany(query, data)
        self.db_con.commit()


    def get_table_uris_targets(self) -> List[Dict[str, Any]]:
        self.db_cur.execute(f"""
            SELECT *
            FROM {DB_TABLE_URIS_TARGETS}
            ORDER BY timestamp ASC
            LIMIT {DISPLAY_LIMIT_SCRAPING_LIST}
        """)
        columns = [desc[0] for desc in self.db_cur.description]
        return [dict(zip(columns, row)) for row in self.db_cur.fetchall()]


    async def update_available_nodes(self) -> None:
        vpn_addresses_availables = (await proxypi.run(PROXYPI_COMMAND_AVAILABLE_NODES)).splitlines()

        for vpn_address in vpn_addresses_availables:
            if vpn_address not in self.scrapers.keys():
                scraper = await ScraperImage.create(vpn_address)
                if any([
                    scraper.hostname in [_.hostname for _ in self.scrapers.values()],
                    scraper.node_id in [_.node_id for _ in self.scrapers.values()],
                    scraper.port in [_.port for _ in self.scrapers.values()],
                ]):
                    print("trying to create a scraper for a scraper id that already exists")
                else:
                    self.scrapers[vpn_address] = scraper

        for scraper in self.scrapers.values():
            if scraper.vpn_address not in vpn_addresses_availables:
                scraper.online = False
            else:
                scraper.online = True


    async def update_nodes(self) -> None:
        for scraper in self.scrapers.values():
            if scraper.online:
                await scraper.update()


    async def update(self) -> None:
        await self.update_available_nodes()
        await self.update_nodes()


    def get_scraper_from_hostname(self, hostname: str) -> Union[ScraperImage, None]:
        for scraper in self.scrapers.values():
            if scraper.hostname == hostname:
                return scraper
        return None
        

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


async def background_update(app):
    while True:
        await app.state.broker.update()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if BROKER_CLEAR_DB_ON_STARTUP and os.path.exists(BROKER_DATABASE):
        os.remove(BROKER_DATABASE)  # automatically created by sqlite3.connect(BROKER_DATABASE)
    app.state.broker = await Broker.create()

    bg_task = asyncio.create_task(background_update(app))
    
    yield
    
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    
    app.state.broker.db_con.close()


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
async def promise_scrape(
    uris: Union[str, List[str]] = Body(...),
    tag: str = Body(None),
):
# async def promise_scrape(uris: Union[HttpUrl, List[HttpUrl]]):
    try:
        app.state.broker.promise_scrape(uris, tag)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/scraping-list")
async def get_table_uris_targets():
    try:
        return app.state.broker.get_table_uris_targets()
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/nodes")
async def nodes():
    try:
        return [
            {
                "online": scraper.online,
                "hostname": scraper.hostname,
                "node_id": scraper.node_id,
                "ram_specs": scraper.ram_specs,
                "ram_usage": scraper.ram_usage,
                "ipv6": scraper.ipv6,
                "browsers": scraper.browsers,
            }
            for scraper in app.state.broker.scrapers.values()
        ]
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
            status_code=409, detail=f"No browser instance {instance_id} for scraper {hostname}"
        )

    url = f"http://{scraper.vpn_address}:{HTTP_PORT_SCRAPER}/stream/{instance_id}"

    client = httpx.AsyncClient()
    req = client.build_request("GET", url)
    response = await client.send(req, stream=True)
    
    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        headers=dict(response.headers),
        background=BackgroundTask(client.aclose)
    )