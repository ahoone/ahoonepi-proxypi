import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone

from contract.schemas.architecture import (
    BrowserModel,
    BrowserModelStatus,
    BrowsingRecord,
)
from contract.schemas.get import ScraperGetRequest
from contract.schemas.new_instance import NewInstanceRequest
from zendriver.core.cloudflare import cf_is_interactive_challenge_present, verify_cf
from zendriver_ext.Tab import TabExt

from scraper.core.DatabaseHandler import DatabaseHandler
from scraper.core.Display import Display
from scraper.core.Driver import Driver
from scraper.core.FrameUnpacker import FrameUnpacker
from scraper.core.models.Browser import RequestWhileClosingError
from scraper.core.Profile import Profile
from scraper.core.schemas import BotSpottedError
from scraper.core.Streamer import Streamer
from scraper.engine.detection import check_cf_blocking_content
from scraper.engine.recovery_period import recovery_period
from scraper.engine.score import score

BROWSER_DEFAULT_WINDOW = (1920, 1080)
GET_QUEUE_MAXSIZE = 6
TIMEOUT_DETECTION_CF_CHALLENGE = 10  # seconds
TIMEOUT_SEARCH_CF_CHALLENGE = 10  # seconds
TIMEOUT_RESOLVE_CF_CHALLENGE = 10  # seconds
TIMEOUT_GET = 60  # seconds
TIMEOUT_GET_CONTENT = 4  # seconds
TIMEOUT_LAZY_LOADING = 10  # seconds
TIMEOUT_DRIVER_GET = 20  # seconds
TIMEOUT_KILL_CANCELLED_TASKS = (
    2  # seconds (short, just accounts for the get_or_abort method)
)

logger = logging.getLogger(__name__)


class Browser:
    """
    maybe a lock should be used to avoid multiple simultaneous call
    are made to the get method
    """

    __event_closing: asyncio.Event
    closed: bool
    created_at: datetime
    expires_at: datetime
    browsing_history: list[BrowsingRecord]
    spotted: bool
    recovery_period: datetime

    profile: Profile
    __display: Display
    __driver: Driver
    __streamer: Streamer
    __frame_unpacker: FrameUnpacker

    active_tasks: set[asyncio.Task]
    __lock_active_tasks: asyncio.Lock
    __lock_get: asyncio.Lock

    initialized: bool

    def __init__(self) -> None:
        """
        Solely used for placeholders elements
        (like reserving UUIDs for a new instance request).
        """
        self.initialized = False

    @classmethod
    async def create(cls, request: NewInstanceRequest) -> "Browser":
        """
        Not thread safe.
        Dangerous to have concurrent calls with the same profile UUIDs to this method.

        Args:
            request (NewInstanceRequest): Description.

        Returns:
            "Browser": Description.
        """
        instance = cls()
        await instance.__initialize(request)
        return instance

    async def __initialize(self, request: NewInstanceRequest) -> None:
        """
        Not thread safe.
        Dangerous to have concurrent calls with the same profile UUIDs to this method.

        Args:
            request (NewInstanceRequest): Description.
        """

        self.__event_closing = asyncio.Event()
        self.closed = False
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(
            seconds=request.lifespan_in_seconds
        )
        self.browsing_history = []
        self.spotted = False
        self.recovery_period = datetime.now(timezone.utc)

        try:
            self.profile = await Profile.create(request)
            self.__display = await Display.create(window_size=BROWSER_DEFAULT_WINDOW)
            self.__driver = await Driver.create(self.__display, self.profile)
            self.__streamer = Streamer(display=self.__display)
            self.__frame_unpacker = FrameUnpacker(streamer=self.__streamer)
        except:
            self.close()
            raise
        finally:
            asyncio.create_task(self.__close())

        self.active_tasks = set()
        self.__lock_active_tasks = asyncio.Lock()
        self.__lock_get = asyncio.Lock()

        self.initialized = True

    def to_model(self) -> BrowserModel:
        return BrowserModel(
            profile=self.profile.to_model(),
            window_size=self.__display.window_size,
            display=self.__display.display,
            created_at=self.created_at,
            expires_at=self.expires_at,
            remaining_lifespan=self.remaining_lifespan(),
            status=self.status(),
            score=score(self.browsing_history),
        )

    def get_browsing_history(self) -> list[BrowsingRecord]:
        return self.browsing_history

    def stream(self):
        return self.__frame_unpacker.stream()

    def status(self) -> BrowserModelStatus:
        if self.closed:
            return "closed"
        elif self.__event_closing.is_set():
            return "closing"
        elif self.__lock_get.locked():
            return "requesting"
        elif self.recovery_period > datetime.now(timezone.utc):
            return "recovering"
        else:
            return "idle"

    def remaining_lifespan(self) -> timedelta:
        return self.expires_at - datetime.now(timezone.utc)

    def expired(self) -> bool:
        """
        Returns `True` if and only if the browser is expired.

        Returns:
            bool: Description.
        """
        return self.expires_at < datetime.now(timezone.utc)

    async def scrape(self, request: ScraperGetRequest) -> BrowsingRecord:
        """
        Thread safe.
        Cannot be used with `asyncio.wait_for` because
        the task is not really cancelled :
        the error is swallowed inside `Browser.get_or_abort`
        and a record is always returned.

        The fix would be to have this function to pass the `BrowsingRecord` reference
        and to have `Browser.get_or_abort` to raise after `asyncio.CancelledError`.

        Args:
            request (ScraperGetRequest): Description.

        Returns:
            BrowsingRecord: Description.

        Raises:
            RequestWhileClosingError: Description.
        """
        if self.__event_closing.is_set():
            raise RequestWhileClosingError
        async with self.__lock_active_tasks:
            task = asyncio.create_task(self.__get_or_abort(request))
            self.active_tasks.add(task)
        try:
            return await task
        finally:
            async with self.__lock_active_tasks:
                self.active_tasks.discard(task)

    async def __get_or_abort(self, request: ScraperGetRequest) -> BrowsingRecord:
        """
        Thread safe.

        Args:
            request (ScraperGetRequest): Description.

        Returns:
            BrowsingRecord: Description.
        """
        browsing_record = BrowsingRecord(url=request.url)
        try:
            async with self.__lock_get:
                delta = (
                    self.recovery_period - datetime.now(timezone.utc)
                ).total_seconds()
                if delta > 0.0:
                    await asyncio.sleep(delta)
                await self.__get(request, browsing_record)
                self.recovery_period = datetime.now(timezone.utc) + timedelta(
                    milliseconds=recovery_period()
                )
        except asyncio.CancelledError:
            browsing_record.status = "aborted"
        finally:
            browsing_record.timestamp = datetime.now(timezone.utc)
            self.browsing_history.append(browsing_record)
        return browsing_record

    async def __get(
        self, request: ScraperGetRequest, browsing_record: BrowsingRecord
    ) -> None:
        """
        Not thread safe.
        Directly updates the given reference to a `BrowsingRecord`.

        Moves the current tab and captures its html content
        - moves the tab,
        - waits for the page to load,
        - checks for challenge (and then solves it),
        - checks for cloudflare blocking the content (by getting first the html content),
        - triggers lazy loading,
        - gets the html content,
        - returns.

        Args:
            request (ScraperGetRequest): Description.
            browsing_record (BrowsingRecord): Description.
        """

        loop = asyncio.get_running_loop()

        start_time = loop.time()
        awaitable = self.__driver.driver.get(
            str(request.url), new_tab=False, new_window=False
        )
        try:
            tab = await asyncio.wait_for(awaitable, TIMEOUT_DRIVER_GET)
        except asyncio.TimeoutError:
            browsing_record.status = "failed"
            return
        browsing_record.timedelta_driver_get = loop.time() - start_time

        # This operation is time self-constrainted
        # (SETTLING_WAIT_TIME_COMPLETE + SETTLING_WAIT_TIME_INTERACTIVE)
        # not counting `tab.evaluate("document.readyState")`
        start_time = loop.time()
        browsing_record.tab_state = await TabExt.smart_wait(tab)
        browsing_record.timedelta_smart_wait = loop.time() - start_time

        awaitable = cf_is_interactive_challenge_present(tab)
        start_time = loop.time()
        try:
            found_challenge = await asyncio.wait_for(
                awaitable, TIMEOUT_SEARCH_CF_CHALLENGE
            )
        except asyncio.TimeoutError:
            found_challenge = False
        browsing_record.timedelta_search_cf_challenge = loop.time() - start_time

        if found_challenge:
            print(f"{request.url} is protected by cloudflare challenge!")
            awaitable = verify_cf(tab)
            start_time = loop.time()
            try:
                await asyncio.wait_for(awaitable, TIMEOUT_RESOLVE_CF_CHALLENGE)
            except asyncio.TimeoutError:
                pass
            browsing_record.timedelta_resolve_cf_challenge = loop.time() - start_time

        start_time = loop.time()
        try:
            await check_cf_blocking_content(tab)
        except BotSpottedError:
            self.spotted = True
            browsing_record.status = "blocked"
            return
        browsing_record.timedelta_check_cf_blocking_content = loop.time() - start_time

        # This element can fail without causing problems
        # We skip this phase is the browser was marked `spotted`
        # at hte prvious step
        if request.flag_lazy_loading and not self.spotted:
            awaitable = await TabExt.trigger_lazy_loading(tab)
            start_time = loop.time()
            try:
                await asyncio.wait_for(awaitable, TIMEOUT_LAZY_LOADING)
            except asyncio.TimeoutError:
                pass
            browsing_record.timedelta_lazy_loading = loop.time() - start_time

        awaitable = tab.get_content()
        start_time = loop.time()
        try:
            browsing_record.html = await asyncio.wait_for(
                awaitable, TIMEOUT_GET_CONTENT
            )
        except asyncio.TimeoutError:
            browsing_record.status = "failed"
            browsing_record.traceback = traceback.format_exc()
            return
        browsing_record.timedelta_get_content = loop.time() - start_time

        browsing_record.status = "success"

    def close(self) -> None:
        """
        Thread safe.
        Immutable effect (can be spammed).
        """
        self.__event_closing.set()

    async def __close(self) -> None:
        """
        Not thread safe.
        Wrapped in a task by the initialization method.
        Waits for the closing event.
        """
        await self.__event_closing.wait()
        await self.__flush_active_tasks()
        await self.__close_components()
        self.closed = True

    async def __flush_active_tasks(self) -> None:
        """Not thread safe."""
        async with self.__lock_active_tasks:
            snapshot_tasks = self.active_tasks.copy()
        for task in snapshot_tasks:
            task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*snapshot_tasks, return_exceptions=True),
                timeout=TIMEOUT_KILL_CANCELLED_TASKS,
            )
        except asyncio.TimeoutError:
            pass
        async with self.__lock_active_tasks:
            for task in snapshot_tasks:
                if task in self.active_tasks:
                    self.active_tasks.discard(task)

    async def __close_components(self) -> None:
        """
        Not thread safe.
        Firstly, kill the driver, the frame unpacker, and the streamer.
        Makes sure to kill the display and the profile after the driver to avoid ending in an unproper state prone to detection.
        """
        await asyncio.gather(
            self.__driver.close(),
            asyncio.to_thread(self.__frame_unpacker.kill),
            asyncio.to_thread(self.__streamer.kill),
        )
        await asyncio.gather(
            self.profile.close(),
            asyncio.to_thread(self.__display.kill),
        )
