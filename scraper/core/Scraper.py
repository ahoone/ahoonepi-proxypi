import asyncio
from typing import Dict, NoReturn, Optional, Set

from Config import Config
from core.Browser import Browser
from core.schemas import GetRequest, NewInstanceRequest


class Scraper:

    def __init__(self) -> None:
        self.browsers: Dict[str, Browser] = {}
        self.__browser_active_tasks: Dict[str, Set[asyncio.Task]] = {}

    def browser_exists(self, instance_id: str) -> bool:
        return instance_id in self.browsers.keys()

    async def new_instance(self, request: Optional[NewInstanceRequest]) -> None:
        self.browsers[request.instance_id] = await Browser.create(
            request.lifespan_in_seconds, request.window_size
        )
        self.__browser_active_tasks[request.instance_id] = set()

    async def get(self, request: GetRequest) -> str:
        task = asyncio.create_task(
            self.browsers[request.instance_id].get_or_abort(request.url)
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
