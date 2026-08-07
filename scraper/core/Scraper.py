import asyncio
import logging
import os
from typing import NoReturn
from uuid import UUID

from contract.Config import Config as ContractConfig
from contract.schemas.architecture import BrowsingRecord, ScraperModel
from contract.schemas.new_instance import NewInstanceRequest
from contract.schemas.scrape import ScraperScrapeRequest

from scraper.Config import Config
from scraper.core.Browser import Browser
from scraper.core.models.Scraper import IdentifierInUse

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self) -> None:
        self.browsers: dict[UUID, Browser] = {}
        self.restarting: bool = False
        self.__lock_browsers: asyncio.Lock = asyncio.Lock()
        self.__lock_update: asyncio.Lock = asyncio.Lock()

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
        async with self.__lock_browsers:
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
        async with self.__lock_browsers:
            return profile_uuid in self.browsers

    async def __book_key(self, profile_uuid: UUID) -> None:
        """
        Thread safe.
        First, checks if `request` has a `profile_uuid` that is available.
        Then, book the `uuid` to the scraper.

        Args:
            profile_uuid (UUID): Description.

        Raises:
            IdentifierInUse: Description.
        """
        async with self.__lock_browsers:
            if profile_uuid in self.browsers:
                e = f"Tried to book a browser slot with a currently used uuid: {profile_uuid}"
                logger.warning(e)
                raise IdentifierInUse(e)
            self.browsers[profile_uuid] = Browser()

    async def __unbook_key(self, profile_uuid: UUID) -> None:
        """
        Thread safe.

        Args:
            profile_uuid (UUID): Description.
        """
        async with self.__lock_browsers:
            if profile_uuid not in self.browsers:
                e = f"Tried to unbook a browser slot that was not book: {profile_uuid}"
                logger.warning(e)
                raise KeyError(e)
            del self.browsers[profile_uuid]

    async def new_instance(self, request: NewInstanceRequest) -> UUID:
        """
        Thread safe.
        Free the `uuid` if the browser creation was not successful.

        Args:
            request (NewInstanceRequest): Description.

        Returns:
            UUID: Description.

        Raises:
            IdentifierInUse: Description.
        """
        is_booking_a_slot = request.profile_uuid is not None

        if is_booking_a_slot:
            await self.__book_key(request.profile_uuid)

        try:
            browser = await Browser.create(request)
        except:
            if is_booking_a_slot:
                await self.__unbook_key(request.profile_uuid)
            raise
        async with self.__lock_browsers:
            self.browsers[browser.uuid] = browser
        return browser.uuid

    async def scrape(self, request: ScraperScrapeRequest) -> BrowsingRecord:
        return await self.browsers[request.profile_uuid].scrape(request)

    def __close_expired_instances(self) -> None:
        [
            browser.close()
            for browser in self.browsers.values()
            if browser.initialized and browser.expired
        ]

    async def __flush_stopped_instances(self) -> None:
        """
        Thread safe.
        """
        async with self.__lock_browsers:
            closed_browsers_uuids = [
                profile_uuid
                for profile_uuid, browser in self.browsers.items()
                if browser.initialized and browser.closed
            ]
            for profile_uuid in closed_browsers_uuids:
                del self.browsers[profile_uuid]

    async def background_update(self) -> NoReturn:
        while True:
            async with self.__lock_update:
                await self.__update()
            await asyncio.sleep(Config.REFRESH_RATE_SCRAPER)

    async def __update(self) -> None:
        await asyncio.gather(
            asyncio.to_thread(self.__close_expired_instances),
            self.__flush_stopped_instances(),
        )

    async def close_browser(self, profile_uuid: UUID) -> None:
        async with self.__lock_browsers:
            self.browsers[profile_uuid].close()

    async def terminate(self) -> None:
        """
        Use `scraper.restarting: bool` in the api endpoints to check if the scraper can receive requests.
        """
        async with self.__lock_update:
            self.restarting = True
            try:
                [browser.close() for browser in self.browsers.values()]
            finally:
                self.restarting = False
