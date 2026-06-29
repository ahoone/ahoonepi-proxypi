import asyncio
import datetime
import random
import traceback
from dataclasses import astuple, dataclass
from itertools import filterfalse
from typing import Any, Dict, List, Literal, NoReturn, Optional, Set
from uuid import UUID, uuid4

from Config import Config
from core.BrowserImage import BrowserImage, BrowserImageGetResult
from core.DatabaseHandler import DatabaseHandler
from core.NodeIdentifier import NodeIdentifier
from core.schemas import ClearRequest, ScrapeRequest
from core.ScraperImage import ScraperImage


@dataclass
class RecordRequest:
    """
    similar to core.BrowserImage.BrowserImageGetResult
    but enhanced with the target_id (int)
    """

    target_id: int
    request_timestamp: float
    response_timestamp: float
    success: bool
    content: str


class Broker:
    def __init__(self) -> None:
        self.scrapers: Dict[int, ScraperImage] = {}  # node_id -> scraper
        self.logger: List[Dict[str, Any]] = []
        self.__lock_logger: asyncio.Lock = asyncio.Lock()
        self.effective_refresh_period: float = None
        self.__current_tasks: Dict[int, asyncio.Task] = {}
        self.__lock_current_tasks: asyncio.Lock = asyncio.Lock()
        self.__lock_hibernate: asyncio.Lock = asyncio.Lock()

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
        query = f"INSERT INTO {Config.DB_TABLE_LOGS} (timestamp, detail, level) VALUES (?, ?, ?)"
        await DatabaseHandler.execute(
            query,
            (event["timestamp"], event["detail"], event["level"]),
        )

    async def scrape(self, request: ScrapeRequest) -> UUID:
        # data = [(request.urls, request.tag)] if isinstance(request.urls, str) else [(url, request.tag) for url in request.urls]
        # NOT SUPPORTING MULTIPLE ELEMENTS AT ONCE
        uuid = uuid4()
        data = [(str(uuid), str(request.url), request.antwortzeit, request.tag)]
        query = f"INSERT INTO {Config.DB_TABLE_TARGETS} (id, url, antwortzeit, tag) VALUES (?, ?, ?, ?)"
        await DatabaseHandler.executemany(query, data)
        return uuid

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
                    AND l.enabled = 1
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

    async def __unwrap_task(
        self,
        target_id: int,
        task: asyncio.Task,
        flag_cancel_if_not_done: bool = False,
    ) -> Optional[RecordRequest]:
        """
        implements a flag to cancel a task if it is not done
        (useful to clean the environment)
        Returns a RecordRequest if the task is done or if the flag_cancel_if_not_done is set to true.
        """
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
            return RecordRequest(
                target_id=target_id,
                request_timestamp=result.request_timestamp,
                response_timestamp=result.response_timestamp,
                success=result.success,
                content=result.content,
            )
        if flag_cancel_if_not_done:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError as e:
                print(f"Cancelletion of task {target_id} failed: {e}")
            return RecordRequest(
                target_id=target_id,
                request_timestamp=datetime.datetime.now(),
                response_timestamp=datetime.datetime.now(),
                success=False,
                content="Task was cancelled due to: flag_cancel_if_not_done",
            )
        return None

    async def __retrieve_tasks(self) -> None:
        """
        retrieves all completed tasks
        remove them from the current tasks dictionnary
        load the records in the database
        """
        async with self.__lock_current_tasks:
            completed: List[Optional[RecordRequest]] = await asyncio.gather(
                *[
                    self.__unwrap_task(target_id, task)
                    for target_id, task in self.__current_tasks.items()
                ]
            )
            completed: List[RecordRequest] = [_ for _ in completed if _]
            for record in completed:
                del self.__current_tasks[record.target_id]
        if len(completed) > 0:
            query = f"""
                INSERT INTO {Config.DB_TABLE_REQUESTS} ({Config.DB_TABLE_TARGETS}_id, request_timestamp, response_timestamp, success, content)
                VALUES (?, ?, ?, ?, ?)
            """
            await DatabaseHandler.executemany(
                query, [astuple(record) for record in completed]
            )

    async def __update(self) -> None:
        try:
            await self.__update_available_nodes()
            await self.__update_nodes()
            await self.__distribute_task()
            await self.__retrieve_tasks()
        except Exception as e:
            traceback.print_exc()

    async def background_update(self) -> NoReturn:
        loop = asyncio.get_running_loop()
        next_update = loop.time()
        last_update = next_update

        while True:
            if self.__lock_hibernate.locked():
                continue
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

    async def cancel_running_tasks(self) -> None:
        """
        cancel scraping tasks saved in ram
        and give them an error code in the database
        """
        async with self.__lock_current_tasks:
            # in here no record is None due to the flag
            completed: List[RecordRequest] = await asyncio.gather(
                *[
                    self.__unwrap_task(target_id, task, flag_cancel_if_not_done=True)
                    for target_id, task in self.__current_tasks.items()
                ]
            )
            if len(completed) > 0:
                query = f"""
                    INSERT INTO {Config.DB_TABLE_REQUESTS} ({Config.DB_TABLE_TARGETS}_id, request_timestamp, response_timestamp, success, content)
                    VALUES (?, ?, ?, ?, ?)
                """
                await DatabaseHandler.executemany(
                    query, [astuple(record) for record in completed]
                )
            self.__current_tasks = {}

    async def clear(self, request: ClearRequest) -> None:
        async with self.__lock_hibernate:
            await self.cancel_running_tasks()
            await asyncio.gather(
                *[
                    scraper.kill_browsers()
                    for scraper in self.scrapers.values()
                    if scraper.online
                ]
            )
            if request.flag_clear_unassigned_targets:
                await DatabaseHandler.clear_unassigned_targets()
