import asyncio
import os
from uuid import UUID, uuid4

import zendriver as uc

from scraper.core.Display import Display

TIMEOUT_DRIVER_STOP = 5  # seconds


class Driver:
    driver: uc.Browser
    __profile_uuid: UUID

    @classmethod
    async def create(cls, display: Display) -> "Driver":
        instance = cls()
        await instance.__initialize(display)
        return instance

    async def __initialize(self, display: Display) -> None:
        self.__profile_uuid = uuid4()
        os.environ["DISPLAY"] = display.display
        self.driver = await uc.start(
            headless=False,  # If headerless, Cloudflare spots us.
            browser_args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                f"--user-data-dir=/tmp/chrome-profile-{self.__profile_uuid}",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                f"--window-size={display.window_size[0]},{display.window_size[1]}",
                "--window-position=0,0",
            ],  # If images are blocked, Cloudflare spots us.
            sandbox=False,
            env={**os.environ},
        )

    async def kill(self) -> None:
        """
        probably never stopping:
        creates a zombie process
        999      4088371  0.0  0.0      0     0 ?        Z    Apr20   0:00 [chrome_crashpad] <defunct>

        The best option would be to track the chromium processn and manually kill it.
        """
        try:
            await asyncio.wait_for(self.driver.stop(), timeout=TIMEOUT_DRIVER_STOP)
        except asyncio.TimeoutError:
            print(f"failed to close the driver {self.__profile_uuid}")
