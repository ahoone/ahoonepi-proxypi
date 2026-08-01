import asyncio
import os
from uuid import UUID

import zendriver as uc

from scraper.core.Display import Display
from scraper.core.Profile import Profile

TIMEOUT_DRIVER_STOP = 600  # seconds


class Driver:
    driver: uc.Browser
    __profile_uuid: UUID

    @classmethod
    async def create(cls, display: Display, profile: Profile) -> "Driver":
        instance = cls()
        await instance.__initialize(display, profile)
        return instance

    async def __initialize(self, display: Display, profile: Profile) -> None:
        self.__profile_uuid = profile.uuid

        os.environ["DISPLAY"] = display.display
        self.driver = await uc.start(
            headless=False,  # If headerless, Cloudflare spots us.
            browser_args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                f"--user-data-dir={profile.user_data_dir}",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                f"--window-size={display.window_size[0]},{display.window_size[1]}",
                "--window-position=0,0",
            ],  # If images are blocked, Cloudflare spots us.
            sandbox=False,
            env={**os.environ},
        )

    async def close(self) -> None:
        """Not thread safe."""
        try:
            await asyncio.wait_for(self.driver.stop(), timeout=TIMEOUT_DRIVER_STOP)
        except asyncio.TimeoutError:
            print(
                f"failed to close the driver {self.__profile_uuid} within {TIMEOUT_DRIVER_STOP} seconds"
            )
