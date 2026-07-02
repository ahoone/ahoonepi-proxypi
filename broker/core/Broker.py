import asyncio
import datetime
import random
import traceback
from typing import Dict, List, Literal, NoReturn, Optional, Set, Tuple
from uuid import UUID, uuid4

from Config import Config
from core.BrowserImage import BrowserImage, BrowserImageGet, BrowserImageGetResult
from core.DatabaseHandler import DatabaseHandler
from core.NodeIdentifier import NodeIdentifier
from core.schemas import ClearRequest, ScrapeRequest, ScrapeRequestResponse
from core.ScraperImage import ScraperImage, ScraperImageModel
from pydantic import BaseModel, Field, HttpUrl


class RecordRequest(BaseModel):
    """
    similar to core.BrowserImage.BrowserImageGetResult
    but enhanced with the target_uuid
    """

    target_uuid: UUID
    request_timestamp: datetime.datetime
    response_timestamp: datetime.datetime
    success: bool
    content: str


class Event(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    detail: str
    level: Literal["DEBUG", "INFO", "WARNING"]


class Broker:
    def __init__(self) -> None:
        self.scrapers: Dict[int, ScraperImage] = {}  # node_id -> scraper
        self.logger: List[Event] = []
        self.__lock_logger: asyncio.Lock = asyncio.Lock()
        self.effective_refresh_period: float = None
        self.__current_tasks: Dict[UUID, asyncio.Task] = {}
        self.__lock_current_tasks: asyncio.Lock = asyncio.Lock()
        self.__lock_hibernate: asyncio.Lock = asyncio.Lock()
        self.__counter_update_loop: int = 0

    def to_model(self) -> List[ScraperImageModel]:
        return [scraper.to_model() for scraper in self.scrapers.values()]

    async def log(
        self,
        detail: str,
        level: Optional[Literal["DEBUG", "INFO", "WARNING"]] = "INFO",
    ) -> None:
        async with self.__lock_logger:
            event = Event(detail=detail, level=level)
            if level != "DEBUG":
                self.logger.insert(0, event)
                self.logger = self.logger[: Config.BUFFER_LOGGER_SIZE]
        query = f"INSERT INTO {Config.DB_TABLE_LOGS} (timestamp, detail, level) VALUES (?, ?, ?)"
        await DatabaseHandler.execute(
            query,
            (event.timestamp, event.detail, event.level),
        )

    async def scrape(self, request: ScrapeRequest) -> ScrapeRequestResponse:
        query = f"""
            INSERT INTO {Config.DB_TABLE_TARGETS}
            (id, url, antwortzeit, tag, flag_lazy_loading)
            VALUES (?, ?, ?, ?, ?)
        """

        async def scrape_url(request: ScrapeRequest) -> ScrapeRequestResponse:
            uuid: UUID = uuid4()
            data: List[Tuple[str, str, datetime.datetime, str, bool]] = [
                (
                    str(uuid),
                    str(request.url),
                    request.antwortzeit,
                    request.tag,
                    request.flag_lazy_loading,
                )
            ]
            await DatabaseHandler.executemany(query, data)
            return ScrapeRequestResponse(uuid=uuid)

        async def scrape_urls(request: ScrapeRequest) -> ScrapeRequestResponse:
            uuids: List[UUID] = []
            data: List[Tuple[str, str, datetime.datetime, str, bool]] = []
            for url in request.url:
                uuid = uuid4()
                uuids.append(uuid)
                data.append(
                    (
                        str(uuid),
                        str(url),
                        request.antwortzeit,
                        request.tag,
                        request.flag_lazy_loading,
                    )
                )
            await DatabaseHandler.executemany(query, data)
            return ScrapeRequestResponse(uuid=uuids)

        if isinstance(request.url, HttpUrl):
            return await scrape_url(request)
        elif isinstance(request.url, list):
            return await scrape_urls(request)
        else:
            raise ValueError("The payload is malformed.")

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

    async def __get_target(self) -> Optional[BrowserImageGet]:
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
            response = await DatabaseHandler.fetchone(query)
            if response:
                return BrowserImageGet(
                    id=response["id"],
                    url=response["url"],
                    flag_lazy_loading=response["flag_lazy_loading"],
                )
            return None

    async def __distribute_task(self) -> None:
        target: Optional[BrowserImageGet] = await self.__get_target()
        if not target:
            await self.log("no target found")
            return
        await self.log(f"selected target {target.url}")
        browser: Optional[BrowserImage] = await self.get_available_browser()
        if not browser:
            await self.log(f"no browser available for {target.id}", level="WARNING")
            return
        await self.log(f"browser {browser.instance_id} selected for {target.id}")
        async with self.__lock_current_tasks:
            self.__current_tasks[target.id] = asyncio.create_task(browser.get(target))

    async def __unwrap_task(
        self,
        target_uuid: UUID,
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
                # print(traceback.format_exc())
                await self.log(
                    f"task {target_uuid} failed: {result.content}",
                    level="WARNING",
                )
            return RecordRequest(
                target_uuid=target_uuid,
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
                print(f"Cancelletion of task {target_uuid} failed: {e}")
            return RecordRequest(
                target_uuid=target_uuid,
                request_timestamp=datetime.datetime.now(),
                response_timestamp=datetime.datetime.now(),
                success=False,
                content="Task was cancelled due to: flag_cancel_if_not_done",
            )
        return None

    async def __load_records(self, records: List[RecordRequest]) -> None:
        query = f"""
            INSERT INTO {Config.DB_TABLE_REQUESTS} ({Config.DB_TABLE_TARGETS}_id, request_timestamp, response_timestamp, success, content)
            VALUES (?, ?, ?, ?, ?)
        """
        await DatabaseHandler.executemany(
            query,
            [
                (
                    str(record.target_uuid),
                    record.request_timestamp,
                    record.response_timestamp,
                    record.success,
                    record.content,
                )
                for record in records
            ],
        )

    async def __retrieve_tasks(self) -> None:
        """
        retrieves all completed tasks
        remove them from the current tasks dictionnary
        load the records in the database
        """
        async with self.__lock_current_tasks:
            completed: List[Optional[RecordRequest]] = await asyncio.gather(
                *[
                    self.__unwrap_task(target_uuid, task)
                    for target_uuid, task in self.__current_tasks.items()
                ]
            )
            completed: List[RecordRequest] = [_ for _ in completed if _]
            for record in completed:
                del self.__current_tasks[record.target_uuid]
        if len(completed) > 0:
            await self.__load_records(completed)

    async def __update(self) -> None:
        """
        we want to skip the update loop if the clearing process is running
        but we also need to make sure that we are not creating a race condition
        (the lock is free -> the update loop is acquired -> takes time to complete)
        (-> at the same time clear is called -> browser is deleted before distributing tasks)
        """
        if self.__lock_hibernate.locked():
            await self.log(
                "broker is hibernating because of clearing method",
                level="WARNING",
            )
            return
        else:
            async with self.__lock_hibernate:
                await self.log(
                    f"Starting update loop: {self.__counter_update_loop}",
                    level="DEBUG",
                )
                try:
                    await self.__update_available_nodes()
                    await self.__update_nodes()
                    await self.__distribute_task()
                    await self.__retrieve_tasks()
                except Exception:
                    traceback.print_exc()
                finally:
                    await self.log(
                        f"Ending update loop: {self.__counter_update_loop}",
                        level="DEBUG",
                    )
                    self.__counter_update_loop += 1

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

    async def get_running_tasks(self) -> List[UUID]:
        async with self.__lock_current_tasks:
            return [_ for _ in self.__current_tasks]

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
                    self.__unwrap_task(target_uuid, task, flag_cancel_if_not_done=True)
                    for target_uuid, task in self.__current_tasks.items()
                ]
            )
            if len(completed) > 0:
                await self.__load_records(completed)
            self.__current_tasks = {}

    async def kill_browsers(self) -> None:
        await asyncio.gather(
            *[
                scraper.kill_browsers()
                for scraper in self.scrapers.values()
                if scraper.online
            ]
        )

    async def clear(self, request: ClearRequest) -> None:
        async with self.__lock_hibernate:
            if request.flag_cancel_running_tasks:
                await self.cancel_running_tasks()
            if request.flag_kill_browsers:
                await self.kill_browsers()
            if request.flag_clear_unassigned_targets:
                await DatabaseHandler.clear_unassigned_targets()
