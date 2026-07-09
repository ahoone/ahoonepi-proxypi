import asyncio
import datetime
from typing import Literal

import zendriver as uc
from contract.schemas.architecture import BrowserModel, BrowsingRecord
from contract.schemas.get import ScraperGetRequest
from contract.schemas.new_instance import NewInstanceRequest
from Config import Config
from core.Display import Display
from core.Driver import Driver
from core.FrameUnpacker import FrameUnpacker
from core.schemas import BotSpottedError
from core.Streamer import Streamer
from engine.detection import herobrine_is_here
from engine.recovery_period import recovery_period
from engine.score import score

MAXIMUM_SIZE_ERROR_MESSAGE = 256
SETTLING_WAIT_TIME_COMPLETE = 1  # seconds
SETTLING_WAIT_TIME_INTERACTIVE = 3  # seconds
GET_QUEUE_MAXSIZE = 6


class Browser:
    """
    maybe a lock should be used to avoid multiple simultaneous call
    are made to the get method
    """

    __display: Display
    __driver: Driver
    __streamer: Streamer
    __frame_unpacker: FrameUnpacker

    __killing_event: asyncio.Event
    __get_lock: asyncio.Lock

    instance_id: str
    window_size: tuple[int, int]
    created_at: datetime.datetime
    expires_at: datetime.datetime
    browsing_history: list[BrowsingRecord]
    spotted: bool
    recovery_period: datetime.datetime

    @classmethod
    async def create(cls, request: NewInstanceRequest) -> "Browser":
        instance = cls()
        await instance.__initialize(request)
        return instance

    async def __initialize(self, request: NewInstanceRequest) -> None:
        self.__display = await Display.create(window_size=request.window_size)
        self.__driver = await Driver.create(display=self.__display)
        self.__streamer = Streamer(display=self.__display)
        self.__frame_unpacker = FrameUnpacker(streamer=self.__streamer)

        self.__killing_event = asyncio.Event()
        self.__get_lock = asyncio.Lock()

        self.instance_id = request.instance_id
        self.window_size = request.window_size
        self.created_at = datetime.datetime.now()
        self.expires_at = self.created_at + datetime.timedelta(
            seconds=request.lifespan_in_seconds
        )
        self.browsing_history = []
        self.spotted = False
        self.recovery_period = datetime.datetime.now()

    def to_model(self) -> BrowserModel:
        return BrowserModel(
            window_size=self.window_size,
            display=self.__display.display,
            created_at=self.created_at,
            expires_at=self.expires_at,
            remaining_lifespan=self.remaining_lifespan(),
            status=self.status(),
            score=self.score(),
            browsing_history=self.browsing_history,
        )

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
    async def smart_wait(page) -> Literal["complete", "interactive", "loading"]:
        """
        tries to wait up for the complete status, but returns with any status after a certain waiting time
        """
        current_state = await page.evaluate("document.readyState")
        if current_state == "complete":
            pass
        elif current_state == "interactive":
            try:
                await page.wait_for_ready_state(
                    until="complete", timeout=SETTLING_WAIT_TIME_COMPLETE
                )
            except asyncio.TimeoutError:
                pass
        else:
            try:
                await page.wait_for_ready_state(
                    until="interactive", timeout=SETTLING_WAIT_TIME_INTERACTIVE
                )
            except asyncio.TimeoutError:
                pass
        current_state = await page.evaluate("document.readyState")
        return current_state

    async def get_or_abort(self, request: ScraperGetRequest) -> str:
        try:
            async with self.__get_lock:
                return await self.get(request)
        except asyncio.CancelledError as e:
            self.browsing_history.append(
                BrowsingRecord(
                    url=request.url,
                    status="aborted",
                    timestamp=datetime.datetime.now().isoformat(),
                )
            )
            raise ValueError(e)

    async def trigger_lazy_loading(self, page: uc.Tab) -> bool:
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

        time_limit = datetime.datetime.now() + datetime.timedelta(
            seconds=Config.TIME_LIMIT_LAZY_LOADING,
        )
        # scroll_height = 0  # percentages of the screen height
        while datetime.datetime.now() < time_limit:
            await page.scroll_down(1000)
            await asyncio.sleep(4)
            return True

        return False

    async def get(self, request: ScraperGetRequest) -> str:
        """
        Moves the current page and captures its html content.

        Args:
            request (GetRequest): .

        Returns:
            str: The html code.

        Raises:
            BotSpottedError: .
        """

        browsing_record = BrowsingRecord(url=request.url)

        delta = (self.recovery_period - datetime.datetime.now()).total_seconds()
        if delta > 0.0:
            await asyncio.sleep(delta)

        try:
            page = await self.__driver.driver.get(
                str(request.url), new_tab=False, new_window=False
            )
            browsing_record.page_state = await self.smart_wait(page)
            self.recovery_period = datetime.datetime.now() + datetime.timedelta(
                milliseconds=recovery_period()
            )
            html = await page.get_content()

            if herobrine_is_here(html):
                self.spotted = True
                raise BotSpottedError(html)
                # should also raise a html error to the broker

            if request.flag_lazy_loading:
                browsing_record.success_lazy_loading = await self.trigger_lazy_loading(
                    page
                )
                html = await page.get_content()

        except BotSpottedError as e:
            browsing_record.status = "blocked"
            browsing_record.html = e.html
            browsing_record.timestamp = (datetime.datetime.now().isoformat(),)
            self.browsing_history.append(browsing_record)
            raise ValueError(e)

        except Exception as e:
            browsing_record.status = "failed"
            browsing_record.error = str(e)
            browsing_record.timestamp = (datetime.datetime.now().isoformat(),)
            self.browsing_history.append(browsing_record)
            raise ValueError(e)

        browsing_record.status = "success"
        browsing_record.timestamp = datetime.datetime.now().isoformat()
        self.browsing_history.append(browsing_record)
        return html

    async def kill(self) -> None:
        await asyncio.gather(
            asyncio.to_thread(self.__frame_unpacker.kill),
            asyncio.to_thread(self.__streamer.kill),
            asyncio.to_thread(self.__display.kill),
        )
        await self.__driver.kill()
