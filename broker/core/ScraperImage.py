import asyncio
import httpx
import json
import requests
from string import Template
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from Config import Config
from core.BrowserImage import BrowserImage
from core.NodeIdentifier import NodeIdentifier

sys.path.insert(0, "/plugins")
import proxypi

PROXYPI_COMMAND_INFO = Template("info $node_id")
TIMEOUT_SCRAPER_HTTP_REQUEST = 4  # seconds


class ScraperImage:

    def __init__(self) -> None:
        self.online: bool = None
        self.passport: NodeIdentifier = None
        self.hostname: str = None  # should be UNIQUE
        self.ipv6: str = None
        self.ram_specs: str = None
        self.ram_usage: str = None
        self.available: bool = False
        # self.electricity_consumption: ?
        self.browsers: Dict[str, BrowserImage] = {}  # instance_id: browser
        self.score: float = 0.0
        self.__lock_updating: asyncio.Lock = asyncio.Lock()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online": self.online,
            "hostname": self.hostname,
            "node_id": self.passport.node_id,
            "passport": self.passport,
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
            PROXYPI_COMMAND_INFO.safe_substitute(node_id=node_id)
        )
        response_as_dict = json.loads(response)
        self.hostname = response_as_dict["hostname"]
        self.ipv6 = response_as_dict["ipv6"]

    async def update(self) -> None:
        async with httpx.AsyncClient() as client:
            try:
                health_response, scraper_response = await asyncio.gather(
                    client.get(
                        f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/health",
                        timeout=TIMEOUT_SCRAPER_HTTP_REQUEST,
                    ),
                    client.get(
                        f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/browsers",
                        timeout=TIMEOUT_SCRAPER_HTTP_REQUEST,
                    ),
                )
            except Exception as e:
                print(e)
                return

        if health_response.status_code == 200:
            health_response_as_dict = json.loads(health_response.text)
            self.available = health_response_as_dict["can_create_browser"]
            self.ram_specs = health_response_as_dict["ram_specs"]
            self.ram_usage = health_response_as_dict["ram_usage"]

        if scraper_response.status_code == 200:
            self.browsers = {}
            for instance_id, browser_as_dict in json.loads(scraper_response.text).items():
                self.browsers[instance_id] = BrowserImage(
                    instance_id, self.passport, browser_as_dict
                )

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
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/new-instance",
                json=payload,
                timeout=TIMEOUT_SCRAPER_HTTP_REQUEST,
            )
            return response.status_code == 201
