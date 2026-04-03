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
from string import Template, ascii_letters, digits
import sys
from typing import Any, Callable, Dict, List, Literal, Union, Optional, Tuple

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware
import proxypi

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "LIGHTHOUSE" in NODE_ROLE, "The node should be a lighthouse (ie includes broker) to launch this image"


BROKER_DATABASE = "broker.db"
BROKER_CLEAR_DB_ON_STARTUP = True
DB_TABLE_URLS_TARGETS = "urls_targets"
DB_TABLE_URLS_RESPONSES = "urls_responses"
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
#         self.url: str = None
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
        self.port: str = None  # UNIQUE (equivalent to primary key)
        self.hostname: str = None  # UNIQUE
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


    async def __fetch(self) -> None:
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


    async def update(self) -> None:
        await self.__fetch()
        # anything to update for the browsers?


    async def available(self) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{self.vpn_address}:{HTTP_PORT_SCRAPER}/available")
            if response.status_code != 200:
                return False
            return json.loads(response.text)["available"]


    async def new_instance(
        self,
        instance_id: str,
        lifespan_in_seconds: Optional[int] = None,
        window_size: Optional[Union[List[int], Tuple[int, int]]] = None,
    ) -> bool:
        async with httpx.AsyncClient() as client:
            payload={"instance_id": instance_id}
            if lifespan_in_seconds:
                payload["lifespan_in_seconds"] = lifespan_in_seconds
            if window_size:
                payload["window_size"] = window_size
            response = await client.post(f"http://{self.vpn_address}:{HTTP_PORT_SCRAPER}/new_instance", json=payload)
            return response.status_code == 200


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class ScrapeRequest(BaseModel):
    url: HttpUrl
    antwortzeit: datetime.datetime  # the time you hope the request to complete
    tag: str


class Broker:

    def __init__(
        self,
    ) -> None:
        self.scrapers: Dict[str, ScraperImage] = {}  # vpn_address -> scraper
        self.__db_con = None
        self.__db_cur = None


    # __INIT__ CAN NOT BE ASYNC IN PYTHON
    @classmethod
    async def create(cls) -> "Broker":
        broker = cls()
        await broker.__initialize()
        return broker


    async def __initialize(self) -> None:
        await self.update()
        self.__db_con = sqlite3.connect(BROKER_DATABASE)
        self.__db_cur = self.__db_con.cursor()
        self.__initialize_db_tables()


    def __initialize_db_tables(self) -> None:
        response = self.__db_cur.execute("SELECT name FROM sqlite_master")
        if response and DB_TABLE_URLS_TARGETS not in response.fetchall():
            self.__db_cur.execute(f"""
                CREATE TABLE {DB_TABLE_URLS_TARGETS} (
                    id INTEGER PRIMARY KEY,
                    url TEXT,
                    antwortzeit DATETIME,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tag TEXT
                );
            """)
        if response and DB_TABLE_URLS_RESPONSES not in response.fetchall():
            self.__db_cur.execute(f"""
                CREATE TABLE {DB_TABLE_URLS_RESPONSES} (
                    url,
                    response,
                    request_timestamp,
                    response_timestamp
                );
            """)


    def scrape(self, request: ScrapeRequest) -> None:
        # data = [(request.urls, request.tag)] if isinstance(request.urls, str) else [(url, request.tag) for url in request.urls]
        # NOT SUPPORTING MULTIPLE ELEMENTS AT ONCE
        data = [(str(request.url), request.antwortzeit, request.tag)]
        query = f"INSERT INTO {DB_TABLE_URLS_TARGETS} (url, antwortzeit, tag) VALUES (?, ?, ?)"
        self.__db_cur.executemany(query, data)
        self.__db_con.commit()


    def scraping_list(self) -> List[Dict[str, Any]]:
        self.__db_cur.execute(f"""
            SELECT *
            FROM {DB_TABLE_URLS_TARGETS}
            ORDER BY antwortzeit ASC
            LIMIT {DISPLAY_LIMIT_SCRAPING_LIST}
        """)
        columns = [desc[0] for desc in self.__db_cur.description]
        return [dict(zip(columns, row)) for row in self.__db_cur.fetchall()]


    async def __update_available_nodes(self) -> None:
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


    async def __update_nodes(self) -> None:
        updates = [
            scraper.update()
            for scraper in self.scrapers.values()
            if scraper.online
        ]
        await asyncio.gather(*updates)


    @staticmethod
    def __random_id():
        return ''.join(random.choices(ascii_letters + digits, k=8))


    async def __create_browser(self) -> bool:
        """
        returns true if successfully creates a browser
        """
        tasks = [
            (vpn_address, scraper.available())
            for vpn_address, scraper in self.scrapers.items()
            if scraper.online
        ]
        results = await asyncio.gather(*[task for _, task in tasks])
        availables = [
            vpn_address 
            for (vpn_address, _), result in zip(tasks, results)
            if result
        ]
        if len(availables) == 0:
            return False
        await self.scrapers[random.choice(availables)].new_instance(self.__random_id())
        return True


    async def __get_available_browser(self) -> BrowserImage:
        """
        returns the object browser that can handle the job
        """
        def get_browsers():
            browsers = []
            [browsers.extend(scraper.browsers.values()) for scraper in self.scrapers.values() if scraper.online]
            return browsers

        browsers = get_browsers()
        if (not browsers) and (await self.__create_browser()):
            browsers = get_browsers()
        return random.choice(browsers) if browsers else None


    async def __distribute(self) -> None:
        # url =
        worker = await self.__get_available_browser() 
        if not worker:
            return


    async def update(self) -> None:
        await self.__update_available_nodes()
        await self.__update_nodes()
        await self.__distribute()


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
    
    app.state.broker.__db_con.close()


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


@app.post("/scrape")
async def scrape(request: ScrapeRequest):
    try:
        app.state.broker.scrape(request)
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/scraping-list")
async def scraping_list():
    try:
        return app.state.broker.scraping_list()
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
