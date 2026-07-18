import asyncio
import datetime
import os
import random
import traceback
from typing import Literal, NoReturn
from uuid import UUID, uuid4

from contract.schemas.architecture import BrowsingRecord
from contract.schemas.get import ScraperGetRequest
from pydantic import HttpUrl

from broker.api.schemas.clear import ClearRequest
from broker.api.schemas.scrape import ScrapeRequest, ScrapeResponse
from broker.Config import Config
from broker.core.BrowserImage import BrowserImage
from broker.core.DatabaseHandler import DatabaseHandler
from broker.core.models.Broker import BrokerModel, Event
from broker.core.models.DatabaseHandler import RecordTarget
from broker.core.NodeIdentifier import NodeIdentifier
from broker.core.ScraperImage import ScraperImage


class Broker:
    def __init__(self) -> None:
        self.scrapers: dict[int, ScraperImage] = {}  # node_id -> scraper
        self.logs: list[Event] = []
        self.__lock_logs: asyncio.Lock = asyncio.Lock()
        self.effective_refresh_period: float | None = None
        self.__current_tasks: dict[UUID, asyncio.Task] = {}
        self.__lock_current_tasks: asyncio.Lock = asyncio.Lock()
        self.__lock_hibernate: asyncio.Lock = asyncio.Lock()
        self.__counter_update_loop: int = 0

    async def __get_running_requests(self) -> list[RecordTarget]:
        uuids = await self.get_running_tasks()
        return await DatabaseHandler.get_targets_from_uuids(uuids)

    async def to_model(self) -> BrokerModel:

        (
            running_requests,
            unscraped_targets,
            scraped_targets,
            nodes,
        ) = await asyncio.gather(
            self.__get_running_requests(),
            DatabaseHandler.get_unscraped_targets(),
            DatabaseHandler.get_scraped_targets(),
            asyncio.to_thread(
                lambda: [scraper.to_model() for scraper in self.scrapers.values()]
            ),
        )

        return BrokerModel(
            is_running_as_root=os.getuid() == 0,
            broker_refresh_period=Config.REFRESH_PERIOD_BROKER,
            broker_effective_refresh_period=self.effective_refresh_period,
            nodes=nodes,
            logs=list(self.logs),
            running_requests=running_requests,
            unscraped_targets=unscraped_targets,
            scraped_targets=scraped_targets,
        )

    async def log(
        self,
        detail: str,
        level: Literal["DEBUG", "INFO", "WARNING"] | None = "INFO",
    ) -> None:
        async with self.__lock_logs:
            event = Event(detail=detail, level=level)
            if level != "DEBUG":
                self.logs.insert(0, event)
                self.logs = self.logs[: Config.BUFFER_LOGGER_SIZE]
        query = f"INSERT INTO {Config.DB_TABLE_LOGS} (timestamp, detail, level) VALUES (?, ?, ?)"
        await DatabaseHandler.execute(
            query,
            (event.timestamp, event.detail, event.level),
        )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        query = f"""
            INSERT INTO {Config.DB_TABLE_TARGETS}
            (uuid, url, expected_response_time, tag, flag_lazy_loading)
            VALUES (?, ?, ?, ?, ?)
        """

        async def scrape_url(request: ScrapeRequest) -> ScrapeResponse:
            uuid: UUID = uuid4()
            data: list[tuple[str, str, datetime.datetime, str, bool]] = [
                (
                    str(uuid),
                    str(request.url),
                    request.expected_response_time,
                    request.tag,
                    request.flag_lazy_loading,
                )
            ]
            await DatabaseHandler.executemany(query, data)
            return ScrapeResponse(uuid=uuid)

        async def scrape_urls(request: ScrapeRequest) -> ScrapeResponse:
            uuids: list[UUID] = []
            data: list[tuple[str, str, datetime.datetime, str, bool]] = []
            for url in request.url:
                uuid = uuid4()
                uuids.append(uuid)
                data.append(
                    (
                        str(uuid),
                        str(url),
                        request.expected_response_time,
                        request.tag,
                        request.flag_lazy_loading,
                    )
                )
            await DatabaseHandler.executemany(query, data)
            return ScrapeResponse(uuid=uuids)

        if isinstance(request.url, HttpUrl):
            return await scrape_url(request)
        elif isinstance(request.url, list):
            return await scrape_urls(request)
        else:
            raise ValueError("The payload is malformed.")

    async def __update_available_nodes(self) -> None:
        await NodeIdentifier.update_reachable_nodes()
        reachable_node_ids: set[int] = NodeIdentifier.reachable_nodes

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
        if not len(availables):
            await self.log("unable to create a new instance", level="WARNING")
            return False
        random_id = f"{random.choice(Config.SCRAPER_ADJECTIVES)} {random.choice(Config.SCRAPER_FIRST_NAMES)}"
        await self.scrapers[random.choice(availables)].new_instance(random_id)
        await self.log(f"created browser {random_id}")
        return True

    async def get_available_browser(self) -> BrowserImage | None:
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

    async def __get_target(self) -> RecordTarget | None:
        async with self.__lock_current_tasks:
            current_tasks_ids_placeholder = "".join(
                [
                    f"AND l.uuid != '{current_id}' "
                    for current_id in self.__current_tasks
                ]
            )
            query = f"""
                SELECT *
                FROM {Config.DB_TABLE_TARGETS} l
                WHERE 1=1
                    {current_tasks_ids_placeholder}
                    AND l.enabled = 1
                ORDER BY l.expected_response_time ASC
            """
            response = await DatabaseHandler.fetchone(query)
            if response:
                return RecordTarget.model_validate(dict(response))
            return None

    async def __distribute_task(self) -> None:
        target: RecordTarget | None = await self.__get_target()
        if not target:
            await self.log("no target found")
            return
        await self.log(f"selected target {target.url}")
        browser: BrowserImage | None = await self.get_available_browser()
        if not browser:
            await self.log(f"no browser available for {target.uuid}", level="WARNING")
            return
        await self.log(f"browser {browser.instance_id} selected for {target.uuid}")
        payload = ScraperGetRequest(
            instance_id=browser.instance_id,
            url=target.url,
            flag_lazy_loading=target.flag_lazy_loading,
        )
        async with self.__lock_current_tasks:
            self.__current_tasks[target.uuid] = asyncio.create_task(
                browser.get(target.uuid, payload)
            )

    async def __unwrap_task(
        self,
        target_uuid: UUID,
        task: asyncio.Task,
        flag_cancel_if_not_done: bool = False,
    ) -> BrowsingRecord | None:
        if task.done():
            # Here we do not examine for task.exception()
            # because BrowserImage.get() is already formatting any exception
            # and task should not be cancelled
            # but should be done to be in this if block
            # (see https://docs.python.org/3/library/asyncio-task.html#asyncio.Task.exception)
            # We need to be careful here about using try/except block
            # because we do not want to swallow the error
            result: BrowsingRecord = task.result()
            if not result.success:
                await self.log(
                    f"task {target_uuid} failed: {result.traceback}",
                    level="WARNING",
                )
            return result
        elif flag_cancel_if_not_done:
            # `BrowserImage.get` swallows the `asyncio.CancelledError`
            # and put it in shape as `BrowsingRecord`
            task.cancel()
            return await task
        return None

    async def __retrieve_tasks(self) -> None:
        """
        retrieves all completed tasks
        remove them from the current tasks dictionnary
        load the records in the database
        """
        async with self.__lock_current_tasks:
            unwrapped: list[BrowsingRecord | None] = await asyncio.gather(
                *[
                    self.__unwrap_task(target_uuid, task)
                    for target_uuid, task in self.__current_tasks.items()
                ]
            )
            completed: list[BrowsingRecord] = [_ for _ in unwrapped if _]
            for record in completed:
                del self.__current_tasks[record.target_uuid]
        if len(completed):
            await DatabaseHandler.insert_job_records(completed)

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
                    await self.__retrieve_tasks()
                    await DatabaseHandler.disable_successfull_targets()
                    await DatabaseHandler.disable_unsuccesfull_targets()
                    await self.__distribute_task()
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

    def get_scraper_from_hostname(self, hostname: str) -> ScraperImage | None:
        for scraper in self.scrapers.values():
            if scraper.hostname == hostname:
                return scraper
        return None

    async def get_running_tasks(self) -> list[UUID]:
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
            completed: list[BrowsingRecord] = await asyncio.gather(
                *[
                    self.__unwrap_task(target_uuid, task, flag_cancel_if_not_done=True)
                    for target_uuid, task in self.__current_tasks.items()
                ]
            )
            if len(completed):
                await DatabaseHandler.insert_job_records(completed)
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
                await DatabaseHandler.disable_unassigned_targets()
