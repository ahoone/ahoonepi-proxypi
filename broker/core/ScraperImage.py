import asyncio
import json
import logging
import traceback
from ipaddress import IPv6Address
from string import Template
from uuid import UUID

import httpx
from contract.schemas.architecture import ScraperModel
from contract.schemas.new_instance import NewInstanceRequest, NewInstanceResponse
from proxypi_socket import proxypi

from broker.Config import Config
from broker.core.BrowserImage import BrowserImage
from broker.core.models.ScraperImage import ScraperImageModel
from broker.core.NodeIdentifier import NodeIdentifier

PROXYPI_COMMAND_INFO = Template("info $node_id")
TIMEOUT_SCRAPER_HTTP_REQUEST = 4  # seconds
TIMEOUT_SCRAPER_HTTP_REQUEST_NEW_INSTANCE = 10  # seconds
REFRESH_PERIOD_SCRAPER = 0.1  # seconds
BACKOFF_REFRESH_PERIOD_SCRAPER = 180  # seconds

logger = logging.getLogger(__name__)


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

    online: bool
    passport: NodeIdentifier
    hostname: str
    ipv6: IPv6Address
    ram_specs: str
    ram_usage: str
    available: bool
    # electricity_consumption: float  # what unit ? over what period ?
    browsers: dict[UUID, BrowserImage]
    # score: float  # score for the proxy ?
    __next_refresh_timestamp: float

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
                        (browser.uuid, browser.to_model())
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
        response = await proxypi.run(
            PROXYPI_COMMAND_INFO.safe_substitute(node_id=node_id)
        )
        response_as_dict = json.loads(response)

        self.online = True
        self.passport = NodeIdentifier(node_id)
        self.hostname = response_as_dict["hostname"]
        self.ipv6 = IPv6Address(response_as_dict["ipv6"])
        self.ram_specs = ""
        self.ram_usage = ""
        self.available = False
        # for demo
        # import random
        # self.ipv6 = IPv6Address(random.getrandbits(128))
        self.browsers = {}
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
            self.ram_specs = scraper_model.ram_specs
            self.ram_usage = scraper_model.ram_usage
            self.available = scraper_model.can_create_browser
            for profile_uuid, browser_model in scraper_model.browsers.items():
                if profile_uuid not in self.browsers:
                    self.browsers[profile_uuid] = await BrowserImage.create(
                        self.passport, browser_model
                    )
            for profile_uuid in self.browsers:
                if profile_uuid not in scraper_model.browsers:
                    del profile_uuid
        except httpx.ReadTimeout:
            logger.warning(
                f"[{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] Took too much time to response. "
                "The remote scraper container must be busy. "
            )
        except httpx.ConnectError:
            logger.warning(
                f"[{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] Unable to connect. "
                f"Will backoff for {BACKOFF_REFRESH_PERIOD_SCRAPER} seconds. "
                "Check for the remote scraper container running. "
            )
            self.__next_refresh_timestamp = loop.time() + BACKOFF_REFRESH_PERIOD_SCRAPER
            return
        except Exception as e:
            logger.error(
                f"[{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] {e}"
            )
            logger.error(traceback.format_exc())
        self.__next_refresh_timestamp = loop.time() + REFRESH_PERIOD_SCRAPER

    async def new_instance(
        self,
        payload: NewInstanceRequest | None = None,
    ) -> UUID:
        if not payload:
            payload = NewInstanceRequest()
        response = await self.passport.client.post(
            f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/new-instance",
            json=payload,
            timeout=TIMEOUT_SCRAPER_HTTP_REQUEST_NEW_INSTANCE,
        )
        response.raise_for_status()
        response_model = NewInstanceResponse.model_validate(response.json())
        return response_model.profile_uuid

    async def close_browsers(self) -> None:
        await asyncio.gather(*[browser.close() for browser in self.browsers.values()])
