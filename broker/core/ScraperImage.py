import asyncio
import json
import sys
import traceback
from ipaddress import IPv6Address
from string import Template

import httpx
from contract.schemas.architecture import ScraperModel

from broker.Config import Config
from broker.core.BrowserImage import BrowserImage
from broker.core.models.ScraperImage import ScraperImageModel
from broker.core.NodeIdentifier import NodeIdentifier

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

    online: bool
    passport: NodeIdentifier
    hostname: str
    ipv6: IPv6Address
    ram_specs: str
    ram_usage: str
    available: bool
    # electricity_consumption: float  # what unit ? over what period ?
    browsers: dict[str, BrowserImage]
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
            self.browsers = {
                instance_id: BrowserImage(instance_id, self.passport, browser_model)
                for instance_id, browser_model in scraper_model.browsers.items()
            }
        except httpx.ReadTimeout:
            print(f"""
                [{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] Took too much time to response.
                The remote scraper container must be busy.
            """)
        except httpx.ConnectError:
            print(f"""
                [{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] Unable to connect.
                Will backoff for {BACKOFF_REFRESH_PERIOD_SCRAPER} seconds.
                Check for the remote scraper container running.
            """)
            self.__next_refresh_timestamp = loop.time() + BACKOFF_REFRESH_PERIOD_SCRAPER
        except Exception as e:
            print(f"[{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}] {e}")
            print(traceback.format_exc())
        finally:
            self.__next_refresh_timestamp = loop.time() + REFRESH_PERIOD_SCRAPER

    async def new_instance(
        self,
        instance_id: str,
        lifespan_in_seconds: int | None = None,
        window_size: tuple[int, int] | None = None,
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
