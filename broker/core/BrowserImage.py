import asyncio
import datetime
from typing import List, Literal

import httpx
from contract.schemas.architecture import BrowserModel
from Config import Config
from core.models.BrowserImage import (
    BrowserImageGet,
    BrowserImageGetResult,
    BrowserImageModel,
)
from core.NodeIdentifier import NodeIdentifier

# this timeout is large because it accounts for lazy loading / others
TIMEOUT_HTTP_SCRAPING = 60  # seconds
TIMEOUT_HTTP_KILL = 10  # seconds


class BrowserImage:
    def __init__(
        self,
        instance_id: str,
        passport: NodeIdentifier,
        browser_model: BrowserModel,
    ) -> None:
        self.instance_id: str = instance_id
        self.passport: NodeIdentifier = passport
        self.created_at: datetime.datetime = browser_model.created_at
        self.expires_at: datetime.datetime = browser_model.expires_at
        self.browsing_history: List[str] = []
        self.status: Literal["idle", "requesting", "spotted", "waiting"] = (
            browser_model.status
        )
        self.score: float = browser_model.score

    def to_model(self) -> BrowserImageModel:
        return BrowserImageModel(
            created_at=self.created_at,
            expires_at=self.expires_at,
            browsing_history=self.browsing_history,
            status=self.status,
            score=self.score,
        )

    async def get(self, payload: BrowserImageGet) -> BrowserImageGetResult:
        """
        should be cancellable
        (therefore response_timestamp is not defined)
        """
        loop = asyncio.get_running_loop()
        request_timestamp = loop.time()
        try:
            response = await self.passport.client.post(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/get",
                json=payload.model_dump(mode="json")
                | {"instance_id": self.instance_id},
                timeout=TIMEOUT_HTTP_SCRAPING,
            )
            success = response.status_code == 200  # Should examine the content
            content = response.json()
        except httpx.TimeoutException as e:
            success = False
            content = str(e)
            print(
                f"Request went timeout on {self.passport.vpn_address}:({self.instance_id}) with error: {e}"
            )
        except Exception as e:
            success = False
            content = str(e)
        response_timestamp = loop.time()
        return BrowserImageGetResult(
            request_timestamp=request_timestamp,
            response_timestamp=response_timestamp,
            success=success,
            content=content,
        )

    async def kill(self) -> bool:
        try:
            response = await self.passport.client.post(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/kill",
                json={"instance_id": self.instance_id},
                timeout=TIMEOUT_HTTP_SCRAPING,
            )
            return response.status_code == 200
        except Exception as e:
            print(
                f"Request went timeout on {self.passport.vpn_address}:({self.instance_id}) with error: {e}"
            )
            return False
