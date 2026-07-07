import asyncio
import os
from typing import Dict, NoReturn, Optional, Set

from common.Config import Config as ContractConfig
from common.schemas.get import ScraperGetRequest
from common.schemas.get_scraper_state import ScraperModel
from common.schemas.new_instance import NewInstanceRequest
from Config import Config
from core.Browser import Browser


class Scraper:
    def __init__(self) -> None:
        self.browsers: Dict[str, Browser] = {}
        self.__browser_active_tasks: Dict[str, Set[asyncio.Task]] = {}

    def to_model(self) -> ScraperModel:
        ram_total, ram_used, ram_free = map(
            int, os.popen("free -b").readlines()[1].split()[1:4]
        )

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

    def browser_exists(self, instance_id: str) -> bool:
        return instance_id in self.browsers.keys()

    async def new_instance(self, request: NewInstanceRequest) -> None:
        self.browsers[request.instance_id] = await Browser.create(
            request.instance_id, request.lifespan_in_seconds, request.window_size
        )
        self.__browser_active_tasks[request.instance_id] = set()

    async def get(self, request: ScraperGetRequest) -> str:
        task = asyncio.create_task(
            self.browsers[request.instance_id].get_or_abort(request)
        )
        self.__browser_active_tasks[request.instance_id].add(task)
        try:
            return await task
        finally:
            self.__browser_active_tasks[request.instance_id].discard(task)

    async def __update(self) -> None:
        expired = [
            self.kill(instance_id)
            for instance_id, browser in self.browsers.items()
            if browser.expired()
        ]
        await asyncio.gather(*expired)

    async def background_update(self) -> NoReturn:
        while True:
            await self.__update()
            await asyncio.sleep(Config.REFRESH_RATE_SCRAPER)

    async def cancel_browser_tasks(self, instance_id: str) -> None:
        tasks = self.__browser_active_tasks[instance_id]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=False)

    async def kill(self, instance_id: str) -> None:
        await self.cancel_browser_tasks(instance_id)
        await self.browsers[instance_id].kill()
        del self.browsers[instance_id]
        del self.__browser_active_tasks[instance_id]

    async def terminate(self) -> None:
        kills = [browser.kill() for browser in self.browsers.values()]
        await asyncio.gather(*kills)
