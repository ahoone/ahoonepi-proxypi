import asyncio
import json
import sys
from ipaddress import IPv6Address
from string import Template
from typing import Dict, List, Optional, Tuple, Union

import httpx
from common.schemas.get_scraper_state import ScraperModel
from Config import Config
from core.BrowserImage import BrowserImage
from core.models.ScraperImage import ScraperImageModel
from core.NodeIdentifier import NodeIdentifier

sys.path.insert(0, "/plugins")
import proxypi

PROXYPI_COMMAND_INFO = Template("info $node_id")
TIMEOUT_SCRAPER_HTTP_REQUEST = 4  # seconds
TIMEOUT_SCRAPER_HTTP_REQUEST_NEW_INSTANCE = 10  # seconds
REFRESH_PERIOD_SCRAPER = 1  # seconds
BACKOFF_REFRESH_PERIOD_SCRAPER = 180  # seconds


class ScraperImage:
    """
    Online is not really a boolean but should be a literal
    -> ['offline', 'online without scraper', 'online with scraper running properly']

    Traceback (most recent call last):
      File "/app/core/Broker.py", line 232, in __update
        await self.__update_available_nodes()
      File "/app/core/Broker.py", line 100, in __update_available_nodes
        self.scrapers[node_id] = await ScraperImage.create(node_id)
      File "/app/core/ScraperImage.py", line 62, in create
        await scraperImage.__initialize(node_id)
      File "/app/core/ScraperImage.py", line 71, in __initialize
        response_as_dict = json.loads(response)
      File "/usr/local/lib/python3.10/json/__init__.py", line 346, in loads
        return _default_decoder.decode(s)
      File "/usr/local/lib/python3.10/json/decoder.py", line 337, in decode
        obj, end = self.raw_decode(s, idx=_w(s, 0).end())
      File "/usr/local/lib/python3.10/json/decoder.py", line 355, in raw_decode
        raise JSONDecodeError("Expecting value", s, err.value) from None
    json.decoder.JSONDecodeError: Expecting value: line 2 column 1 (char 1)
    """

    def __init__(self) -> None:
        self.online: bool = None
        self.passport: NodeIdentifier = None
        self.hostname: str = None  # should be UNIQUE
        self.ipv6: IPv6Address = None
        self.ram_specs: str = None
        self.ram_usage: str = None
        self.available: bool = False
        # self.electricity_consumption: ?
        self.browsers: Dict[str, BrowserImage] = {}  # instance_id: browser
        self.score: float = 0.0
        self.__lock_updating: asyncio.Lock = asyncio.Lock()
        self.__next_refresh_timestamp: float = None

    def to_model(self) -> ScraperImageModel:

        return ScraperImageModel(
            online=self.online,
            hostname=self.hostname,
            node_id=self.passport.node_id,
            passport=self.passport.to_model(),
            ram_specs=self.ram_specs,
            ram_usage=self.ram_usage,
            ipv6=self.ipv6,
            browsers=dict(
                sorted(
                    [
                        (browser.instance_id, browser.to_model())
                        for browser in self.browsers.values()
                    ],
                    key=lambda browser: browser[1].created_at,
                )
            ),
        )

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
        self.ipv6 = IPv6Address(response_as_dict["ipv6"])
        # import random

        # self.ipv6 = IPv6Address(random.getrandbits(128))
        self.__next_refresh_timestamp = asyncio.get_event_loop().time()

    async def update(self) -> None:
        loop = asyncio.get_event_loop()
        if loop.time() < self.__next_refresh_timestamp:
            return
        try:
            scraper_response = await self.passport.client.get(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/get_scraper_state",
                timeout=TIMEOUT_SCRAPER_HTTP_REQUEST,
            )
            scraper_response.raise_for_status()
            scraper_model: ScraperModel = ScraperModel.model_validate(
                scraper_response.json()
            )
            self.available = scraper_model.can_create_browser
            self.ram_specs = scraper_model.ram_specs
            self.ram_usage = scraper_model.ram_usage
            self.browsers = {
                instance_id: BrowserImage(instance_id, self.passport, browser_model)
                for instance_id, browser_model in scraper_model.browsers
            }
        except httpx.ConnectError:
            print(
                f"Unable to connect to {self.passport.vpn_address}. Will backoff for {BACKOFF_REFRESH_PERIOD_SCRAPER} seconds. Check for the scraper container running."
            )
            self.__next_refresh_timestamp = loop.time() + BACKOFF_REFRESH_PERIOD_SCRAPER
            return
        except Exception as e:
            print(f"[{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] {e}")
            return
        self.__next_refresh_timestamp = loop.time() + REFRESH_PERIOD_SCRAPER

    async def new_instance(
        self,
        instance_id: str,
        lifespan_in_seconds: Optional[int] = None,
        window_size: Optional[Union[List[int], Tuple[int, int]]] = None,
    ) -> bool:
        payload = {"instance_id": instance_id}
        if lifespan_in_seconds:
            payload["lifespan_in_seconds"] = lifespan_in_seconds
        if window_size:
            payload["window_size"] = window_size
        response = await self.passport.client.post(
            f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/new-instance",
            json=payload,
            timeout=TIMEOUT_SCRAPER_HTTP_REQUEST_NEW_INSTANCE,
        )
        return response.status_code == 201

    async def kill_browsers(self) -> None:
        await asyncio.gather(*[browser.kill() for browser in self.browsers.values()])
