import aiosqlite
import asyncio
from contextlib import asynccontextmanager
import datetime
import exrex
from fastapi import Body, FastAPI, status, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
    StreamingResponse,
)
import httpx
import ipaddress
import json
import os
from ping3 import ping
from pydantic import HttpUrl, BaseModel, Field
import random
import requests
from starlette.background import BackgroundTask
from string import Template, ascii_letters, digits
import subprocess
import sys
import traceback
from typing import Any, Callable, Dict, List, Literal, Union, Optional, Tuple, Set

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware
import proxypi

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #

HTTP_PORT_SCRAPER = os.environ["HTTP_PORT_SCRAPER"]
NODE_ID_RANGE_REGEX = os.environ["NODE_ID_RANGE_REGEX"]
NODE_ROLE = os.environ["NODE_ROLE"].split(",")
SSH_NETWORK_PREFIX = os.environ["SSH_NETWORK_PREFIX"]
WIREGUARD_LIGHTHOUSE_ID = os.environ["WIREGUARD_LIGHTHOUSE_ID"]
WIREGUARD_NETWORK_PREFIX = os.environ["WIREGUARD_NETWORK_PREFIX"]

assert (
    "LIGHTHOUSE" in NODE_ROLE
), f"The node should be a lighthouse (ie includes broker in {NODE_ROLE}) to launch this image"

BROKER_DATABASE = "/tmp/broker.db"
BROKER_CLEAR_DB_ON_STARTUP = True
DB_TABLE_TARGETS = "targets"
DB_TABLE_REQUESTS = "requests"
DISPLAY_LIMIT_SCRAPING_LIST = 200
LOGGER_BUFFER_SIZE = 10
PROXYPI_COMMAND_AVAILABLE_NODES = "ping-wireguard -a"
PROXYPI_COMMAND_INFO = Template("info $node_id")
PROXYPI_COMMAND_RAM = Template("ram $node_id")
REFRESH_PERIOD_BROKER = 1  # seconds
SEMAPHORE_UPDATE_REACHABLE_NODES = 200
THRESHOLD_SCORE = 300
TIMEOUT_SCRAPER_FETCHING_INFO = 2  # seconds
TIMEOUT_SCRAPER_HTTP_REQUEST = 4  # seconds
TIMEOUT_SCRAPER_PING = 0.1  # seconds


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class NodeIdentifier:

    node_ids: Set[int] = {
        int(x)
        for x in exrex.generate(
            NODE_ID_RANGE_REGEX, limit=exrex.count(NODE_ID_RANGE_REGEX)
        )
    }
    reachable_nodes: Set[int] = None

    @staticmethod
    async def ping(
        host: str,
        port: int,
        sem: asyncio.Semaphore,
    ) -> bool:
        async with sem:
            try:
                conn = asyncio.open_connection(host, port)
                reader, writer = await asyncio.wait_for(conn, TIMEOUT_SCRAPER_PING)
                writer.close()
                await writer.wait_closed()
                return True
            except ConnectionRefusedError:
                return True
            except asyncio.TimeoutError:
                return False
            except OSError:
                return False

    @classmethod
    async def update_reachable_nodes(cls) -> None:
        """
        Only checks if the nodes is accessible,
        independently of the remote scraper container running properly.
        Change ping(..., None, ...) to the desired port (HTTP_PORT_SCRAPER).
        """
        sem = asyncio.Semaphore(SEMAPHORE_UPDATE_REACHABLE_NODES)
        pings = [
            cls.ping(f"{WIREGUARD_NETWORK_PREFIX}.{node_id}", None, sem)
            for node_id in cls.node_ids
        ]
        ping_results = await asyncio.gather(*pings)
        cls.reachable_nodes = {
            node_id
            for node_id, ping_result in zip(cls.node_ids, ping_results)
            if ping_result
        }

    def __init__(self, node_id: int) -> None:
        """
        This method should check for already used node_id.
        """
        if node_id not in NodeIdentifier.node_ids:
            raise ValueError("Invalid node_id")
        self.node_id: int = node_id
        self.vpn_address: str = f"{WIREGUARD_NETWORK_PREFIX}.{node_id}"
        self.ssh_port: int = int(
            f"{SSH_NETWORK_PREFIX}{str(node_id).zfill(len(str(max(NodeIdentifier.node_ids))))}"
        )

    async def available(self) -> bool:
        """
        deprecated, classmethod update reachable nodes is more powerful
        """
        response = await asyncio.to_thread(
            ping,
            self.vpn_address,
            timeout=TIMEOUT_SCRAPER_PING,
        )
        return response is not None


class BrowserImage:

    def __init__(
        self,
        instance_id: str,
        passport: NodeIdentifier,
        scraper_response: Dict[str, Any],
    ) -> None:
        self.instance_id: str = instance_id
        self.passport: NodeIdentifier = passport
        self.created_at: datetime.datetime = scraper_response["created_at"]
        self.expires_at: datetime.datetime = scraper_response["expires_at"]
        self.browsing_history: List[str] = []
        self.status: Literal["idle", "requesting", "spotted", "waiting"] = (
            scraper_response["status"]
        )
        self.score: float = scraper_response["score"]

    async def get(self, url: str):
        """
        should be cancellable
        (therefore response_timestamp is not defined)
        """
        async with httpx.AsyncClient() as client:
            loop = asyncio.get_running_loop()
            request_timestamp = loop.time()
            response = await client.post(
                f"http://{self.passport.vpn_address}:{HTTP_PORT_SCRAPER}/get",
                json={"instance_id": self.instance_id, "url": url},
            )
            response_timestamp = loop.time()
            return {
                "request_timestamp": request_timestamp,
                "response_timestamp": response_timestamp,
                "success": True,  # Should examine the content
                "content": response.json(),
            }


class ScraperImage:

    def __init__(self) -> None:
        self.online: bool = None
        self.passport: NodeIdentifier = None
        self.hostname: str = None  # UNIQUE
        self.ipv6: str = None
        self.ram_specs: str = None
        self.ram_usage: str = None
        # self.electricity_consumption: ?
        self.browsers: Dict[str, BrowserImage] = {}  # instance_id: browser
        self.score: float = 0.0
        self.__lock_updating: asyncio.Lock = asyncio.Lock()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online": self.online,
            "hostname": self.hostname,
            "node_id": self.passport.node_id,
            "ram_specs": self.ram_specs,
            "ram_usage": self.ram_usage,
            "ipv6": self.ipv6,
            "browsers": dict(
                sorted(self.browsers.items(), key=lambda x: x[1].created_at)
            ),
        }

    @classmethod
    async def create(cls, node_id: int) -> "ScraperImage":
        scraperImage = cls()
        await scraperImage.__initialize(node_id)
        return scraperImage

    async def __initialize(self, node_id: int) -> None:
        self.online = True
        self.passport = NodeIdentifier(node_id)
        response = await proxypi.run(
            PROXYPI_COMMAND_INFO.safe_substitute(node_id=self.passport.node_id)
        )
        self.__dict__.update(json.loads(response))

    async def __fetch_info(self) -> None:
        ram_response = await proxypi.run(
            PROXYPI_COMMAND_RAM.safe_substitute(node_id=self.passport.node_id)
        )
        data = json.loads(ram_response)
        self.ram_specs = data["ram_specs"]
        self.ram_usage = data["ram_usage"]

        self.browsers = {}
        scraper_response = requests.get(
            f"http://{self.passport.vpn_address}:{HTTP_PORT_SCRAPER}/browsers",
            timeout=TIMEOUT_SCRAPER_FETCHING_INFO,  # the timeout seems to block the update
        )
        scraper_response_as_dict = json.loads(scraper_response.text)
        if not scraper_response.ok:
            return
        for instance_id, browser_as_dict in scraper_response_as_dict.items():
            self.browsers[instance_id] = BrowserImage(
                instance_id, self.passport, browser_as_dict
            )

        # dropping outdated/killed instances
        # emptying self.browsers may be too memory intensive because of the browsing history
        # but the BrowserImage just on top is always reloading everything...

    async def update(self) -> None:
        await self.__fetch_info()
        # anything to update for the browsers?

    async def available(self) -> bool: 
        """
        the MAX_INSTANCES_PER_SCRAPER should be move in an overall config file
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{self.passport.vpn_address}:{HTTP_PORT_SCRAPER}/available"
            )
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
            payload = {"instance_id": instance_id}
            if lifespan_in_seconds:
                payload["lifespan_in_seconds"] = lifespan_in_seconds
            if window_size:
                payload["window_size"] = window_size
            response = await client.post(
                f"http://{self.passport.vpn_address}:{HTTP_PORT_SCRAPER}/new-instance",
                json=payload,
                timeout=TIMEOUT_SCRAPER_HTTP_REQUEST,
            )
            return response.status_code == 201


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class GetRequest(BaseModel):
    url: str


class ScrapeRequest(BaseModel):
    """
    antwortzeit is the time you hope the response
    default is the time of receiving the request
    else is an isoformat string of datetime.datetime
    """

    url: HttpUrl
    antwortzeit: Optional[datetime.datetime] = Field(
        default_factory=datetime.datetime.now
    )
    tag: str


class DatabaseHandler:

    @classmethod
    async def initialize(cls) -> None:

        async with aiosqlite.connect(BROKER_DATABASE) as conn:

            if BROKER_CLEAR_DB_ON_STARTUP and os.path.exists(BROKER_DATABASE):
                os.remove(BROKER_DATABASE)

            response = await conn.execute("SELECT name FROM sqlite_master")
            if not response:
                return
            existing_tables = await response.fetchall()

            if DB_TABLE_TARGETS not in existing_tables:
                await DatabaseHandler.execute(f"""
                    CREATE TABLE {DB_TABLE_TARGETS} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        antwortzeit DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        tag TEXT
                    );
                """)

            if DB_TABLE_REQUESTS not in existing_tables:
                await DatabaseHandler.execute(f"""
                    CREATE TABLE {DB_TABLE_REQUESTS} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        {DB_TABLE_TARGETS}_id INTEGER NOT NULL,
                        request_timestamp DATETIME NOT NULL,
                        response_timestamp DATETIME,
                        success BOOLEAN,
                        content BLOB,
                        FOREIGN KEY ({DB_TABLE_TARGETS}_id) REFERENCES {DB_TABLE_TARGETS}(id)
                    );
                """)

            # await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.commit()

    @classmethod
    async def execute(cls, query: str, params: Tuple[Any] = None) -> None:
        """
        handlers not aiming for reuse (does not return a cursor)
        but here we only have just one type of fetch per query
        """
        async with aiosqlite.connect(BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(query, params)
            await conn.commit()

    @classmethod
    async def executemany(cls, query: str, params: Tuple[Any] = None) -> None:
        async with aiosqlite.connect(BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executemany(query, params)
            await conn.commit()

    @classmethod
    async def fetchone(cls, query: str, params: Tuple[Any] = None) -> Dict[str, Any]:
        async with aiosqlite.connect(BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, params)
            return await cursor.fetchone()

    @classmethod
    async def fetchall(cls, query: str, params: Tuple[Any] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, params)
            return await cursor.fetchall()


class Broker:

    def __init__(self) -> None:
        self.scrapers: Dict[int, ScraperImage] = {}  # node_id -> scraper
        self.logger: List[Dict[str, Any]] = []
        self.__lock_logger: asyncio.Lock = asyncio.Lock()
        self.effective_refresh_period: float = None
        self.__current_tasks: Dict[int, asyncio.Task] = {}
        self.__lock_current_tasks: asyncio.Lock = asyncio.Lock()

    def to_dict(self) -> Dict[str, Any]:
        return [scraper.to_dict() for scraper in app.state.broker.scrapers.values()]

    async def log(
        self,
        detail: str,
        level: Optional[Literal["INFO", "WARNING"]] = "INFO",
    ) -> None:
        async with self.__lock_logger:
            event = {
                "timestamp": datetime.datetime.now().isoformat(),
                "detail": detail,
                "level": level,
            }
            self.logger.insert(0, event)
            self.logger = self.logger[:LOGGER_BUFFER_SIZE]

    async def scrape(self, request: ScrapeRequest) -> None:
        # data = [(request.urls, request.tag)] if isinstance(request.urls, str) else [(url, request.tag) for url in request.urls]
        # NOT SUPPORTING MULTIPLE ELEMENTS AT ONCE
        data = [(str(request.url), request.antwortzeit, request.tag)]
        query = (
            f"INSERT INTO {DB_TABLE_TARGETS} (url, antwortzeit, tag) VALUES (?, ?, ?)"
        )
        await DatabaseHandler.executemany(query, data)

    async def get_scraping_list(self) -> List[Dict[str, Any]]:
        query = (f"""
            SELECT *
            FROM {DB_TABLE_TARGETS} l
            WHERE 1=1
                AND NOT EXISTS (
                    SELECT 1
                    FROM {DB_TABLE_REQUESTS} r
                    WHERE 1=1
                        AND r.{DB_TABLE_TARGETS}_id = l.id
                        AND r.success = TRUE
                )
            ORDER BY antwortzeit ASC
            LIMIT {DISPLAY_LIMIT_SCRAPING_LIST}
        """)
        return await DatabaseHandler.fetchall(query)

    async def __update_available_nodes(self) -> None:
        await NodeIdentifier.update_reachable_nodes()
        reachable_node_ids: Set[int] = NodeIdentifier.reachable_nodes

        for node_id in reachable_node_ids:
            if node_id not in self.scrapers.keys():
                self.scrapers[node_id] = await ScraperImage.create(node_id)

        for scraper in self.scrapers.values():
            if scraper.passport.node_id not in reachable_node_ids:
                scraper.online = False
            else:
                scraper.online = True

    async def __update_nodes(self) -> None:
        updates = [
            scraper.update() for scraper in self.scrapers.values() if scraper.online
        ]
        await asyncio.gather(*updates)

    @staticmethod
    def __random_id() -> str:
        return "".join(random.choices(ascii_letters + digits, k=8))

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
            vpn_address for (vpn_address, _), result in zip(tasks, results) if result
        ]
        if len(availables) == 0:
            await self.log("unable to create a new instance", level="WARNING")
            return False
        random_id = self.__random_id()
        await self.scrapers[random.choice(availables)].new_instance(random_id)
        await self.log(f"created browser {random_id}")
        return True

    async def get_available_browser(self) -> BrowserImage:
        """
        returns the object (BrowserImage) browser that can handle the job
        """

        def get_browsers():
            browsers = []
            [
                browsers.extend(
                    [
                        browser
                        for browser in scraper.browsers.values()
                        if browser.status == "idle" and browser.score < THRESHOLD_SCORE
                    ]
                )
                for scraper in self.scrapers.values()
                if scraper.online
            ]
            return browsers

        browsers = get_browsers()
        if (not browsers) and (await self.__create_browser()):
            browsers = get_browsers()
        return random.choice(browsers) if browsers else None

    async def __get_target(self) -> Optional[Dict[str, Any]]:
        async with self.__lock_current_tasks:
            query = (f"""
                SELECT *
                FROM {DB_TABLE_TARGETS} l
                WHERE 1=1
                    {''.join([f'AND l.id != {current_id} ' for current_id in self.__current_tasks])}
                    AND NOT EXISTS (
                        SELECT 1
                        FROM {DB_TABLE_REQUESTS} r
                        WHERE 1=1
                            AND r.{DB_TABLE_TARGETS}_id = l.id
                            AND r.success = TRUE
                    )
                ORDER BY l.antwortzeit ASC
            """)
            return await DatabaseHandler.fetchone(query)

    async def __distribute_task(self) -> None:
        target = await self.__get_target()
        if not target:
            await self.log("no target found")
            return
        await self.log(f"selected target {target['id']} ({target['url']})")
        browser = await self.get_available_browser()
        if not browser:
            await self.log(f"no browser available for {target['id']}", level="WARNING")
            return
        await self.log(f"browser {browser.instance_id} selected for {target['id']}")
        task = asyncio.create_task(browser.get(target["url"]))
        async with self.__lock_current_tasks:
            self.__current_tasks[target['id']] = task

    async def __retrieve_task(self) -> None:
        completed: List[Tuple[Any]] = []
        async with self.__lock_current_tasks:
            for target_id, task in self.__current_tasks.items():
                if task.done():
                    result = task.result()
                    completed.append((target_id, result["request_timestamp"], result["response_timestamp"], result["success"], result["content"]))
            for x in completed:
                del self.__current_tasks[x[0]]
        if len(completed) > 0:
            query = f"""
                INSERT INTO {DB_TABLE_REQUESTS} ({DB_TABLE_TARGETS}_id, request_timestamp, response_timestamp, success, content)
                VALUES (?, ?, ?, ?, ?)
            """
            await DatabaseHandler.executemany(query, completed)

    async def update(self) -> None:
        try:
            await self.__update_available_nodes()
            await self.__update_nodes()
            await self.__distribute_task()
            await self.__retrieve_task()
        except Exception as e:
            traceback.print_exc()

    def get_scraper_from_hostname(self, hostname: str) -> Optional[ScraperImage]:
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

    loop = asyncio.get_running_loop()
    next_update = loop.time()
    last_update = next_update

    while True:
        await app.state.broker.update()
        now = loop.time()

        app.state.broker.effective_refresh_period = now - last_update
        last_update = now
        next_update += REFRESH_PERIOD_BROKER
        sleep_time = next_update - loop.time()
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await DatabaseHandler.initialize()
    app.state.broker = Broker()
    bg_task = asyncio.create_task(background_update(app))

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
        "broker_refresh_period": REFRESH_PERIOD_BROKER,
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

    url = f"http://{scraper.passport.vpn_address}:{HTTP_PORT_SCRAPER}/stream/{instance_id}"

    client = httpx.AsyncClient()
    req = client.build_request("GET", url)
    response = await client.send(req, stream=True)

    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        headers=dict(response.headers),
        background=BackgroundTask(client.aclose),
    )
