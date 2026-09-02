import asyncio
from typing import Literal, NoReturn

import zendriver as uc

SETTLING_WAIT_TIME_COMPLETE = 1  # seconds
SETTLING_WAIT_TIME_INTERACTIVE = 3  # seconds


class TabExt:
    @staticmethod
    async def smart_wait(tab: uc.Tab) -> Literal["complete", "interactive", "loading"]:
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
            except TimeoutError:
                pass
        else:
            try:
                await tab.wait_for_ready_state(
                    until="interactive", timeout=SETTLING_WAIT_TIME_INTERACTIVE
                )
            except TimeoutError:
                pass
        current_state = await tab.evaluate("document.readyState")
        return current_state

    @staticmethod
    async def trigger_lazy_loading(tab: uc.Tab) -> NoReturn:
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
