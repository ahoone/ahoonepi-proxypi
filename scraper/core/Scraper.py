import asyncio
import os
from typing import Dict, NoReturn, Set

from common.Config import Config as ContractConfig
from common.schemas.architecture import ScraperModel
from common.schemas.get import ScraperGetRequest
from common.schemas.new_instance import NewInstanceRequest
from Config import Config
from core.Browser import Browser


class Scraper:
    def __init__(self) -> None:
        self.browsers: Dict[str, Browser] = {}
        self.busy: bool = False
        self.__browser_active_tasks: Dict[str, Set[asyncio.Task]] = {}
        self.__lock: asyncio.Lock = asyncio.Lock()
        self.__lock_terminate: asyncio.Lock = asyncio.Lock()
        self.__lock_pending_kills: asyncio.Lock = asyncio.Lock()
        self.__pending_kills: Set[asyncio.Task] = set()

    async def to_model(self) -> ScraperModel:
        ram_total, ram_used, ram_free = map(
            int, os.popen("free -b").readlines()[1].split()[1:4]
        )
        async with self.__lock:
            return ScraperModel(
                is_running_as_root=os.getuid() == 0,
                can_create_browser=len(self.browsers)
                < ContractConfig.MAX_INSTANCES_PER_SCRAPER,
                ram_specs=f"{ram_total // 1024**3}GiB",
                ram_usage=f"{(100 * ram_used) // ram_total}%",
                browsers={
                    instance_id: browser.to_model()
                    for instance_id, browser in self.browsers.items()
                },
            )

    async def browser_exists(self, instance_id: str) -> bool:
        async with self.__lock:
            return instance_id in self.browsers.keys()

    async def new_instance(self, request: NewInstanceRequest) -> None:
        browser = await Browser.create(request)
        async with self.__lock:
            self.browsers[request.instance_id] = browser
            self.__browser_active_tasks[request.instance_id] = set()

    async def get(self, request: ScraperGetRequest) -> str:
        async with self.__lock:
            task = asyncio.create_task(
                self.browsers[request.instance_id].get_or_abort(request)
            )
            self.__browser_active_tasks[request.instance_id].add(task)
        try:
            return await task
        finally:
            async with self.__lock:
                self.__browser_active_tasks[request.instance_id].discard(task)

    async def kill(self, instance_id: str) -> None:

        async with self.__lock:
            tasks = self.__browser_active_tasks[instance_id]

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        pending_kill_task = asyncio.create_task(
            self.browsers[instance_id].kill()
        )  # browser.kill() may create a zombie process (not fixable, due to Xfvb, chromium and ffmepg)
        async with self.__lock_pending_kills:
            self.__pending_kills.add(pending_kill_task)
            # pending_kill_task.add_done_callback(lambda t:
            #     self.__pending_kills.discard(t),
            #     t.exception() and print(f"browser.kill() failed for {instance_id}: {t.exception()}")
            # )

        async with self.__lock:
            del self.browsers[instance_id]
            del self.__browser_active_tasks[instance_id]

    async def __update(self) -> None:
        """
        The only purpose of update is to drop expired browsers.
        """
        async with self.__lock:
            expired_instances = [
                instance_id
                for instance_id, browser in self.browsers.items()
                if browser.expired()
            ]
        to_kill = [self.kill(instance_id) for instance_id in expired_instances]
        await asyncio.gather(*to_kill)

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
                kills = [self.kill(instance_id) for instance_id in self.browsers]
                await asyncio.gather(*kills)
            finally:
                self.busy = False
