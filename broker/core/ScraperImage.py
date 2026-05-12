import asyncio
import httpx
import json
import requests
from string import Template
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from core.BrowserImage import BrowserImage
from core.Config import Config
from core.NodeIdentifier import NodeIdentifier

sys.path.insert(0, "/plugins")
import proxypi

PROXYPI_COMMAND_INFO = Template("info $node_id")
PROXYPI_COMMAND_RAM = Template("ram $node_id")
TIMEOUT_SCRAPER_FETCHING_INFO = 2  # seconds
TIMEOUT_SCRAPER_HTTP_REQUEST = 4  # seconds


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
        # SHOULD BE UPGRADED TO HTTPX
        scraper_response = requests.get(
            f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/browsers",
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
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/available"
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
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/new-instance",
                json=payload,
                timeout=TIMEOUT_SCRAPER_HTTP_REQUEST,
            )
            return response.status_code == 201
