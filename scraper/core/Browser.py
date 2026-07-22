import asyncio
import datetime
import traceback
from typing import Literal
from uuid import UUID, uuid4

import zendriver as uc
from contract.schemas.architecture import BrowserModel, BrowsingRecord
from contract.schemas.get import ScraperGetRequest
from contract.schemas.new_instance import NewInstanceRequest
from scraper.core.Profile import Profile
from zendriver.core.cloudflare import cf_is_interactive_challenge_present, verify_cf

from scraper.core.Display import Display
from scraper.core.Driver import Driver
from scraper.core.FrameUnpacker import FrameUnpacker
from scraper.core.schemas import BotSpottedError
from scraper.core.Streamer import Streamer
from scraper.engine.detection import check_cf_blocking_content
from scraper.engine.recovery_period import recovery_period
from scraper.engine.score import score

SETTLING_WAIT_TIME_COMPLETE = 1  # seconds
SETTLING_WAIT_TIME_INTERACTIVE = 3  # seconds
GET_QUEUE_MAXSIZE = 6
TIMEOUT_DETECTION_CF_CHALLENGE = 10  # seconds
TIMEOUT_SEARCH_CF_CHALLENGE = 10  # seconds
TIMEOUT_RESOLVE_CF_CHALLENGE = 10  # seconds
TIMEOUT_GET = 60  # seconds
TIMEOUT_GET_CONTENT = 4  # seconds
TIMEOUT_LAZY_LOADING = 10  # seconds
TIMEOUT_DRIVER_GET = 20  # seconds

BROWSER_DEFAULT_LIFESPAN = 3600  # 1 hour in seconds
BROWSER_DEFAULT_WINDOW = (1920, 1080)


class Browser:
    """
    maybe a lock should be used to avoid multiple simultaneous call
    are made to the get method
    """

    initialized: bool
    profile_uuid: UUID
    profile_name: str
    browsing_history: list[BrowsingRecord]
    active_tasks: set[asyncio.Task]
    killing_task: asyncio.Task

    __profile: Profile
    __display: Display
    __driver: Driver
    __streamer: Streamer
    __frame_unpacker: FrameUnpacker

    __get_lock: asyncio.Lock

    window_size: tuple[int, int]
    created_at: datetime.datetime
    expires_at: datetime.datetime

    spotted: bool
    recovery_period: datetime.datetime

    def __init__(self) -> None:
        """
        Solely used for placeholders elements.
        Like reserving UUIDs for a new instance request.
        """
        self.initialized = False

    @classmethod
    async def create(cls, profile_uuid: UUID) -> "Browser":
        instance = cls()
        await instance.__initialize(profile_uuid)
        return instance

    async def __initialize(self, profile_uuid: UUID) -> None:
        """checks here if the profile exists in the database and load it"""
        self.profile_uuid = uuid4()

        self.__display = await Display.create(window_size=BROWSER_DEFAULT_WINDOW)
        self.__driver = await Driver.create(
            display=self.__display, profile_uuid=self.__profile.uuid
        )
        self.__streamer = Streamer(display=self.__display)
        self.__frame_unpacker = FrameUnpacker(streamer=self.__streamer)

        self.__get_lock = asyncio.Lock()

        self.profile_name = request.profile_name
        self.window_size = BROWSER_DEFAULT_WINDOW
        self.created_at = datetime.datetime.now()
        self.expires_at = self.created_at + datetime.timedelta(
            seconds=BROWSER_DEFAULT_LIFESPAN
        )
        self.browsing_history = []
        self.spotted = False
        self.recovery_period = datetime.datetime.now()

        self.initialized = True

    def to_model(self) -> BrowserModel:
        return BrowserModel(
            window_size=self.window_size,
            display=self.__display.display,
            created_at=self.created_at,
            expires_at=self.expires_at,
            remaining_lifespan=self.remaining_lifespan(),
            status=self.status(),
            score=self.score(),
            browsing_history=[],  # self.browsing_history,
        )

    def stream(self):
        return self.__frame_unpacker.stream()

    def status(self) -> Literal["idle", "requesting", "spotted", "waiting"]:
        if self.spotted:
            return "spotted"
        elif self.__get_lock.locked():
            return "requesting"
        elif self.recovery_period > datetime.datetime.now():
            return "waiting"
        else:
            return "idle"

    def score(self) -> float:
        return score(self.browsing_history)

    def remaining_lifespan(self) -> datetime.timedelta:
        return self.expires_at - datetime.datetime.now()

    def expired(self) -> bool:
        """
        true if EXPIRED and false if alive
        """
        return self.expires_at < datetime.datetime.now()

    @staticmethod
    async def __smart_wait(tab) -> Literal["complete", "interactive", "loading"]:
        """
        tries to wait up for the complete status, but returns with any status after a certain waiting time
        """
        current_state = await tab.evaluate("document.readyState")
        if current_state == "complete":
            pass
        elif current_state == "interactive":
            try:
                await tab.wait_for_ready_state(
                    until="complete", timeout=SETTLING_WAIT_TIME_COMPLETE
                )
            except asyncio.TimeoutError:
                pass
        else:
            try:
                await tab.wait_for_ready_state(
                    until="interactive", timeout=SETTLING_WAIT_TIME_INTERACTIVE
                )
            except asyncio.TimeoutError:
                pass
        current_state = await tab.evaluate("document.readyState")
        return current_state

    async def get_or_abort(self, request: ScraperGetRequest) -> BrowsingRecord:
        """
        Thread safe.

        Args:
            request (ScraperGetRequest): Description.

        Returns:
            BrowsingRecord: Description.
        """
        browsing_record = BrowsingRecord(url=request.url)
        try:
            async with self.__get_lock:
                delta = (self.recovery_period - datetime.datetime.now()).total_seconds()
                if delta > 0.0:
                    await asyncio.sleep(delta)
                await self.__get(request, browsing_record)
                self.recovery_period = datetime.datetime.now() + datetime.timedelta(
                    milliseconds=recovery_period()
                )
        except asyncio.CancelledError:
            browsing_record.status = "aborted"
        finally:
            browsing_record.timestamp = datetime.datetime.now()
            self.browsing_history.append(browsing_record)
        return browsing_record

    async def __trigger_lazy_loading(self, tab: uc.Tab) -> None:
        """
        INCOMPLETE
        Should:
            - scroll down repeatedly
            - wait for network idle
            - wait for dom stabilization
            - very images are complete
            - no keywords like "skeleton", "anim_skeleton", "bg-c_skeleton"

        Returns:
            bool: True if achieved network inactivity in given time.
        """

        # scroll_height = 0  # percentages of the screen height
        while True:
            await tab.scroll_down(1000)
            await asyncio.sleep(1)

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
        browsing_record.tab_state = await self.__smart_wait(tab)
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
            awaitable = self.__trigger_lazy_loading(tab)
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

    async def kill(self) -> None:
        """
        Not thread safe.
        Firstly, kill the driver, the frame unpacker, and the streamer.
        Makes sure to kill the display after the driver to avoid ending in an unproper state prone to detection.
        """
        await asyncio.gather(
            self.__driver.kill(),
            asyncio.to_thread(self.__frame_unpacker.kill),
            asyncio.to_thread(self.__streamer.kill),
        )
        await asyncio.to_thread(self.__display.kill)
