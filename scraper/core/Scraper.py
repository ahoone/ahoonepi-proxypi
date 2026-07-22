import asyncio
import logging
import os
from typing import NoReturn
from uuid import UUID

from contract.Config import Config as ContractConfig
from contract.schemas.architecture import BrowsingRecord, ScraperModel
from contract.schemas.get import ScraperGetRequest
from contract.schemas.new_instance import NewInstanceRequest
from pydantic import BaseModel

from scraper.Config import Config
from scraper.core.Browser import Browser

logger = logging.getLogger(__name__)

TIMEOUT_KILL_CANCELLED_TASKS = (
    2  # seconds (short, just accounts for the get_or_abort method)
)


class Scraper:
    def __init__(self) -> None:
        self.browsers: dict[UUID, Browser] = {}
        self.busy: bool = False
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

        ram_total, ram_used, ram_free = self.__read_memory_info()
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

        Args:
            profile_uuid (UUID): Description.

        Returns:
            bool: Description.
        """
        async with self.__lock:
            return profile_uuid in self.browsers.keys()

    async def new_instance(self, profile_uuid: UUID) -> None:
        """
        Thread safe.

        Args:
            profile_uuid (UUID): Description.
        """
        async with self.__lock:
            if profile_uuid in self.browsers.keys():
                logger.warning(
                    f"Tried to create a browser instance with an existing uuid: {profile_uuid}"
                )
                return
            self.browsers[profile_uuid] = Browser()
        browser = await Browser.create(profile_uuid)
        async with self.__lock:
            self.browsers[profile_uuid] = browser

    async def get(self, request: ScraperGetRequest) -> BrowsingRecord:
        """
        Cannot be used with `asyncio.wait_for` because
        the task is not really cancelled :
        the error is swallowed inside `Browser.get_or_abort`
        and a record is always returned.

        The fix would be to have this function to pass the `BrowsingRecord` reference
        and to have `Browser.get_or_abort` to raise after `asyncio.CancelledError`.
        """
        async with self.__lock:
            task = asyncio.create_task(
                self.browsers[request.profile_uuid].get_or_abort(request)
            )
            self.__browser_active_tasks[request.profile_uuid].add(task)
        try:
            result = await task
        finally:
            async with self.__lock:
                # race condition:
                # kill could have dropped the profile_uuid while we did not have the lock
                # so we let kill discards the tasks
                if request.profile_uuid in self.__browser_active_tasks:
                    self.__browser_active_tasks[request.profile_uuid].discard(task)
        return result

    async def kill(self, profile_uuid: UUID) -> None:
        """
        Thread safe.
        Firstly, removes logically the browser instance.
        Then, proceeds to clean up and keeps a reference.

        Args:
            profile_uuid (UUID): Description.
        """
        async with self.__lock:
            browser = self.browsers.pop(profile_uuid)
            snapshot_tasks = self.__browser_active_tasks.pop(profile_uuid)

        for task in snapshot_tasks:
            # not a problem to cancel it even if it was done
            task.cancel()

        try:
            await asyncio.wait_for(
                asyncio.gather(*snapshot_tasks, return_exceptions=True),
                timeout=TIMEOUT_KILL_CANCELLED_TASKS,
            )
        except asyncio.TimeoutError:
            pass

        async with self.__lock_browser_death_row:
            # Not guaranteed to terminate quickly.
            self.__browser_death_row[profile_uuid] = asyncio.create_task(browser.kill())

    async def __kill_expired_instances(self) -> None:
        async with self.__lock:
            expired_instances = [
                profile_uuid
                for profile_uuid, browser in self.browsers.items()
                if browser.initialized and browser.expired()
            ]
        to_kill = [self.kill(profile_uuid) for profile_uuid in expired_instances]
        await asyncio.gather(*to_kill)

    async def __check_on_death_row(self) -> None:
        async with self.__lock_browser_death_row:
            completed = [
                profile_uuid
                for profile_uuid, task in self.__browser_death_row.items()
                if task.done()
            ]
            for profile_uuid in completed:
                del self.__browser_death_row[profile_uuid]

    async def __update(self) -> None:
        await asyncio.gather(
            self.__kill_expired_instances(),
            self.__check_on_death_row(),
        )

    async def background_update(self) -> NoReturn:
        while True:
            async with self.__lock_terminate:
                await self.__update()
            await asyncio.sleep(Config.REFRESH_RATE_SCRAPER)

    async def terminate(self) -> None:
        """
        Use `scraper.busy: bool` in the api endpoints to check if the scraper can receive requests.
        """
        async with self.__lock_terminate:
            self.busy = True
            try:
                kills = [self.kill(profile_uuid) for profile_uuid in self.browsers]
                await asyncio.gather(*kills)
            finally:
                self.busy = False
