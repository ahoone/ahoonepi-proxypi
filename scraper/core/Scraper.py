import asyncio
import logging
import os
from typing import NoReturn
from uuid import UUID

from contract.Config import Config as ContractConfig
from contract.schemas.architecture import BrowsingRecord, ScraperModel
from contract.schemas.get import ScraperGetRequest
from contract.schemas.new_instance import NewInstanceRequest

from scraper.Config import Config
from scraper.core.Browser import Browser

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self) -> None:
        self.browsers: dict[UUID, Browser] = {}
        self.restarting: bool = False
        self.__lock: asyncio.Lock = asyncio.Lock()
        self.__lock_terminate: asyncio.Lock = asyncio.Lock()

    @staticmethod
    def __read_memory_info() -> tuple[int, int, int]:
        with open("/proc/meminfo") as f:
            memory_info = {}
            for line in f:
                key, value = line.split(":", 1)
                memory_info[key] = int(value.strip().split()[0]) * 1024  # kB -> bytes
        total = memory_info["MemTotal"]
        free = memory_info["MemFree"]
        available = memory_info.get("MemAvailable", free)
        used = total - available
        return total, used, free

    async def to_model(self) -> ScraperModel:
        """
        Thread safe.

        Returns:
            ScraperModel: Description.
        """
        async with self.__lock:
            snapshot_browsers = list(self.browsers.items())

        ram_total, ram_used, _ = self.__read_memory_info()
        return ScraperModel(
            is_running_as_root=os.getuid() == 0,
            can_create_browser=len(self.browsers)
            < ContractConfig.MAX_INSTANCES_PER_SCRAPER,
            ram_specs=f"{ram_total // 1024**3}GiB",
            ram_usage=f"{(100 * ram_used) // ram_total}%",
            browsers={
                profile_uuid: browser.to_model()
                for profile_uuid, browser in snapshot_browsers
            },
        )

    async def browser_exists(self, profile_uuid: UUID) -> bool:
        """
        Thread safe.
        Return `True` if and only if the browser with the given profile uuid is currently used.

        Args:
            profile_uuid (UUID): Description.

        Returns:
            bool: Description.
        """
        async with self.__lock:
            return profile_uuid in self.browsers

    async def new_instance(self, request: NewInstanceRequest) -> None:
        """
        Thread safe.

        Args:
            profile_uuid (UUID): Description.
        """
        async with self.__lock:
            if request.profile_uuid in self.browsers:
                logger.warning(
                    f"Tried to create a browser instance with a currentlu used uuid: {request.profile_uuid}"
                )
                return
            self.browsers[request.profile_uuid] = Browser()
        browser = await Browser.create(request.profile_uuid)
        async with self.__lock:
            self.browsers[request.profile_uuid] = browser

    async def scrape(self, request: ScraperGetRequest) -> BrowsingRecord:
        return await self.browsers[request.profile_uuid].scrape(request)

    def __close_expired_instances(self) -> None:
        [
            browser.close()
            for browser in self.browsers.values()
            if browser.initialized and browser.expired()
        ]

    async def __flush_stopped_instances(self) -> None:
        """
        Thread safe.
        """
        async with self.__lock:
            closed_browsers_uuids = [
                profile_uuid
                for profile_uuid, browser in self.browsers.items()
                if browser.initialized and browser.closed
            ]
            for profile_uuid in closed_browsers_uuids:
                del self.browsers[profile_uuid]

    async def background_update(self) -> NoReturn:
        while True:
            async with self.__lock_terminate:
                await self.__update()
            await asyncio.sleep(Config.REFRESH_RATE_SCRAPER)

    async def __update(self) -> None:
        await asyncio.gather(
            asyncio.to_thread(self.__close_expired_instances),
            self.__flush_stopped_instances(),
        )

    async def terminate(self) -> None:
        """
        Use `scraper.restarting: bool` in the api endpoints to check if the scraper can receive requests.
        """
        async with self.__lock_terminate:
            self.restarting = True
            try:
                kills = [browser.close() for browser in self.browsers.values()]
                await asyncio.gather(*kills)
            finally:
                self.restarting = False
