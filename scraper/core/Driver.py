import asyncio
import os
from uuid import UUID

import zendriver as uc

from scraper.core.Display import Display

TIMEOUT_DRIVER_STOP = 60  # seconds


class Driver:
    driver: uc.Browser
    __profile_uuid: UUID

    @classmethod
    async def create(cls, display: Display, profile_uuid: UUID) -> "Driver":
        instance = cls()
        await instance.__initialize(display, profile_uuid)
        return instance

    async def __initialize(self, display: Display, profile_uuid: UUID) -> None:
        self.__profile_uuid = profile_uuid
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
        """Not thread safe."""
        try:
            await asyncio.wait_for(self.driver.stop(), timeout=TIMEOUT_DRIVER_STOP)
        except asyncio.TimeoutError:
            print(f"failed to close the driver {self.__profile_uuid}")
        # finally:
