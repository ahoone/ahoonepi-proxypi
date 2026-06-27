import asyncio
import datetime
import random
import traceback
from typing import Any, Dict, List, Literal, NoReturn, Optional, Set, Tuple
from uuid import UUID, uuid4

from Config import Config
from core.BrowserImage import BrowserImage, BrowserImageGetResult
from core.DatabaseHandler import DatabaseHandler
from core.NodeIdentifier import NodeIdentifier
from core.schemas import CollectRequest, ScrapeRequest
from core.ScraperImage import ScraperImage


class Broker:
    def __init__(self) -> None:
        self.scrapers: Dict[int, ScraperImage] = {}  # node_id -> scraper
        self.logger: List[Dict[str, Any]] = []
        self.__lock_logger: asyncio.Lock = asyncio.Lock()
        self.effective_refresh_period: float = None
        self.__current_tasks: Dict[int, asyncio.Task] = {}
        self.__lock_current_tasks: asyncio.Lock = asyncio.Lock()

    def to_dict(self) -> List[Dict[str, Any]]:
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
        # await

    async def scrape(self, request: ScrapeRequest) -> UUID:
        # data = [(request.urls, request.tag)] if isinstance(request.urls, str) else [(url, request.tag) for url in request.urls]
        # NOT SUPPORTING MULTIPLE ELEMENTS AT ONCE
        uuid = uuid4()
        data = [(str(uuid), str(request.url), request.antwortzeit, request.tag)]
        query = f"INSERT INTO {Config.DB_TABLE_TARGETS} (id, url, antwortzeit, tag) VALUES (?, ?, ?, ?)"
        await DatabaseHandler.executemany(query, data)
        return uuid

    async def collect(self, request: CollectRequest) -> Dict[str, Any]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_REQUESTS}
            WHERE 1=1
                AND success = TRUE
                AND {Config.DB_TABLE_TARGETS}_id = '{request.uuid}'
            ORDER BY id ASC
        """
        return await DatabaseHandler.fetchone(query)

    async def get_unscraped_targets(self) -> List[Dict[str, Any]]:
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
            LIMIT {Config.LIMIT_SQL_QUERIES}
        """
        return await DatabaseHandler.fetchall(query)

    async def get_scraped_targets(self) -> List[Dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_REQUESTS}
            WHERE success = TRUE
            ORDER BY id ASC
            LIMIT {Config.LIMIT_SQL_QUERIES}
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

    async def __create_browser(self) -> bool:
        """
        returns true if successfully creates a browser
        """
        availables = [
            scraper.passport.node_id
            for scraper in self.scrapers.values()
            if scraper.available
        ]
        if len(availables) == 0:
            await self.log("unable to create a new instance", level="WARNING")
            return False
        random_id = f"{random.choice(Config.SCRAPER_ADJECTIVES)} {random.choice(Config.SCRAPER_FIRST_NAMES)}"
        await self.scrapers[random.choice(availables)].new_instance(random_id)
        await self.log(f"created browser {random_id}")
        return True

    async def get_available_browser(self) -> Optional[BrowserImage]:
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
                        if browser.status == "idle"
                        and browser.score < Config.THRESHOLD_SCORE
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
            current_tasks_ids_placeholder = "".join(
                [f"AND l.id != '{current_id}' " for current_id in self.__current_tasks]
            )
            query = f"""
                SELECT *
                FROM {Config.DB_TABLE_TARGETS} l
                WHERE 1=1
                    {current_tasks_ids_placeholder}
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
        await self.log(f"selected target {target['url']}")
        browser = await self.get_available_browser()
        if not browser:
            await self.log(f"no browser available for {target['id']}", level="WARNING")
            return
        await self.log(f"browser {browser.instance_id} selected for {target['id']}")
        async with self.__lock_current_tasks:
            self.__current_tasks[target["id"]] = asyncio.create_task(
                browser.get(target["url"])
            )

    async def __retrieve_task(self) -> None:
        completed: List[Tuple[int, float, float, bool, str]] = []
        async with self.__lock_current_tasks:
            for target_id, task in self.__current_tasks.items():
                if task.done():
                    # Here we do not examine for task.exception()
                    # because BrowserImage.get() is already formatting any exception
                    # and task should not be cancelled
                    # but should be done to be in this if block
                    # (see https://docs.python.org/3/library/asyncio-task.html#asyncio.Task.exception)
                    # We need to be careful here about using try/except block
                    # because we do not want to swallow the error
                    result: BrowserImageGetResult = task.result()
                    if not result.success:
                        await self.log(
                            f"task {target_id} failed: {result.content}",
                            level="WARNING",
                        )
                    completed.append(
                        (
                            target_id,
                            result.request_timestamp,
                            result.response_timestamp,
                            result.success,
                            result.content,
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

    async def terminate(self) -> None:
        await asyncio.gather(
            *(scraper.passport.close_client() for scraper in self.scrapers.values()),
            return_exceptions=True,
        )
