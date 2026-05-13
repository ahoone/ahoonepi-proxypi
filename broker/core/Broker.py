import asyncio
import datetime
import random
import traceback
from typing import Any, Dict, List, Literal, NoReturn, Optional, Set, Tuple

from Config import Config
from core.BrowserImage import BrowserImage
from core.DatabaseHandler import DatabaseHandler
from core.NodeIdentifier import NodeIdentifier
from core.ScraperImage import ScraperImage
from core.schemas import ScrapeRequest


class Broker:

    def __init__(self) -> None:
        self.scrapers: Dict[int, ScraperImage] = {}  # node_id -> scraper
        self.logger: List[Dict[str, Any]] = []
        self.__lock_logger: asyncio.Lock = asyncio.Lock()
        self.effective_refresh_period: float = None
        self.__current_tasks: Dict[int, asyncio.Task] = {}
        self.__lock_current_tasks: asyncio.Lock = asyncio.Lock()

    def to_dict(self) -> Dict[str, Any]:
        return [scraper.to_dict() for scraper in self.scrapers.values()]

    async def log(
        self,
        detail: str,
        level: Optional[Literal["INFO", "WARNING"]] = "INFO",
    ) -> None:
        async with self.__lock_logger:
            event = {
                "timestamp": datetime.datetime.now().isoformat(),
                "detail": detail,
                "level": level,
            }
            self.logger.insert(0, event)
            self.logger = self.logger[: Config.BUFFER_LOGGER_SIZE]

    async def scrape(self, request: ScrapeRequest) -> None:
        # data = [(request.urls, request.tag)] if isinstance(request.urls, str) else [(url, request.tag) for url in request.urls]
        # NOT SUPPORTING MULTIPLE ELEMENTS AT ONCE
        data = [(str(request.url), request.antwortzeit, request.tag)]
        query = f"INSERT INTO {Config.DB_TABLE_TARGETS} (url, antwortzeit, tag) VALUES (?, ?, ?)"
        await DatabaseHandler.executemany(query, data)

    async def get_scraping_list(self) -> List[Dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS} l
            WHERE 1=1
                AND NOT EXISTS (
                    SELECT 1
                    FROM {Config.DB_TABLE_REQUESTS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_id = l.id
                        AND r.success = TRUE
                )
            ORDER BY antwortzeit ASC
            LIMIT {Config.BUFFER_SCRAPING_LIST}
        """
        return await DatabaseHandler.fetchall(query)

    async def __update_available_nodes(self) -> None:
        await NodeIdentifier.update_reachable_nodes()
        reachable_node_ids: Set[int] = NodeIdentifier.reachable_nodes

        for node_id in reachable_node_ids:
            if node_id not in self.scrapers.keys():
                self.scrapers[node_id] = await ScraperImage.create(node_id)

        for scraper in self.scrapers.values():
            if scraper.passport.node_id not in reachable_node_ids:
                scraper.online = False
            else:
                scraper.online = True

    async def __update_nodes(self) -> None:
        updates = [
            scraper.update() for scraper in self.scrapers.values() if scraper.online
        ]
        await asyncio.gather(*updates)

    @staticmethod
    def __random_id() -> str:
        return "".join(random.choices(ascii_letters + digits, k=8))

    async def __create_browser(self) -> bool:
        """
        returns true if successfully creates a browser
        """
        tasks = [
            (vpn_address, scraper.available())
            for vpn_address, scraper in self.scrapers.items()
            if scraper.online
        ]
        results = await asyncio.gather(*[task for _, task in tasks])
        availables = [
            vpn_address for (vpn_address, _), result in zip(tasks, results) if result
        ]
        if len(availables) == 0:
            await self.log("unable to create a new instance", level="WARNING")
            return False
        random_id = self.__random_id()
        await self.scrapers[random.choice(availables)].new_instance(random_id)
        await self.log(f"created browser {random_id}")
        return True

    async def get_available_browser(self) -> BrowserImage:
        """
        returns the object (BrowserImage) browser that can handle the job
        """

        def get_browsers():
            browsers = []
            [
                browsers.extend(
                    [
                        browser
                        for browser in scraper.browsers.values()
                        if browser.status == "idle" and browser.score < THRESHOLD_SCORE
                    ]
                )
                for scraper in self.scrapers.values()
                if scraper.online
            ]
            return browsers

        browsers = get_browsers()
        if (not browsers) and (await self.__create_browser()):
            browsers = get_browsers()
        return random.choice(browsers) if browsers else None

    async def __get_target(self) -> Optional[Dict[str, Any]]:
        async with self.__lock_current_tasks:
            query = f"""
                SELECT *
                FROM {Config.DB_TABLE_TARGETS} l
                WHERE 1=1
                    {''.join([f'AND l.id != {current_id} ' for current_id in self.__current_tasks])}
                    AND NOT EXISTS (
                        SELECT 1
                        FROM {Config.DB_TABLE_REQUESTS} r
                        WHERE 1=1
                            AND r.{Config.DB_TABLE_TARGETS}_id = l.id
                            AND r.success = TRUE
                    )
                ORDER BY l.antwortzeit ASC
            """
            return await DatabaseHandler.fetchone(query)

    async def __distribute_task(self) -> None:
        target = await self.__get_target()
        if not target:
            await self.log("no target found")
            return
        await self.log(f"selected target {target['id']} ({target['url']})")
        browser = await self.get_available_browser()
        if not browser:
            await self.log(f"no browser available for {target['id']}", level="WARNING")
            return
        await self.log(f"browser {browser.instance_id} selected for {target['id']}")
        task = asyncio.create_task(browser.get(target["url"]))
        async with self.__lock_current_tasks:
            self.__current_tasks[target["id"]] = task

    async def __retrieve_task(self) -> None:
        completed: List[Tuple[Any]] = []
        async with self.__lock_current_tasks:
            for target_id, task in self.__current_tasks.items():
                if task.done():
                    result = task.result()
                    completed.append(
                        (
                            target_id,
                            result["request_timestamp"],
                            result["response_timestamp"],
                            result["success"],
                            result["content"],
                        )
                    )
            for x in completed:
                del self.__current_tasks[x[0]]
        if len(completed) > 0:
            query = f"""
                INSERT INTO {Config.DB_TABLE_REQUESTS} ({Config.DB_TABLE_TARGETS}_id, request_timestamp, response_timestamp, success, content)
                VALUES (?, ?, ?, ?, ?)
            """
            await DatabaseHandler.executemany(query, completed)

    async def __update(self) -> None:
        try:
            await self.__update_available_nodes()
            await self.__update_nodes()
            await self.__distribute_task()
            await self.__retrieve_task()
        except Exception as e:
            traceback.print_exc()

    async def background_update(self) -> NoReturn:
        loop = asyncio.get_running_loop()
        next_update = loop.time()
        last_update = next_update

        while True:
            await self.__update()
            now = loop.time()
            self.effective_refresh_period = now - last_update
            last_update = now
            next_update += Config.REFRESH_PERIOD_BROKER
            sleep_time = next_update - loop.time()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    def get_scraper_from_hostname(self, hostname: str) -> Optional[ScraperImage]:
        for scraper in self.scrapers.values():
            if scraper.hostname == hostname:
                return scraper
        return None
