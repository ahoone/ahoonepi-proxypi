import asyncio
import datetime
import traceback
from typing import Literal
from uuid import UUID

import httpx
from contract.schemas.architecture import BrowserModel, BrowsingRecord
from contract.schemas.get import ScraperGetRequest

from broker.Config import Config
from broker.core.models.BrowserImage import BrowserImageModel
from broker.core.NodeIdentifier import NodeIdentifier

# this timeout is large because it accounts for lazy loading / others
TIMEOUT_HTTP_SCRAPING = 120  # seconds
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
        self.browsing_history: list[BrowsingRecord] = browser_model.browsing_history
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

    async def get(
        self, target_uuid: UUID, payload: ScraperGetRequest
    ) -> BrowsingRecord:
        """
        Swallows `asyncio.CancelledError`
        """
        try:
            response = await self.passport.client.post(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/get",
                json=payload.model_dump(mode="json"),
                timeout=TIMEOUT_HTTP_SCRAPING,
            )
        except httpx.TimeoutException:
            return BrowsingRecord(
                target_uuid=target_uuid,
                url=payload.url,
                status="timeout",
                traceback=traceback.format_exc(),
            )
        except asyncio.CancelledError:
            return BrowsingRecord(
                target_uuid=target_uuid,
                url=payload.url,
                status="aborted",
                traceback=traceback.format_exc(),
            )

        if response.status_code != 200:
            return BrowsingRecord(
                target_uuid=target_uuid,
                url=payload.url,
                status="implementation_error",
                http_error_code=response.status_code,
                traceback=response.json()["detail"],
            )

        record = BrowsingRecord.model_validate(response.json())
        record.target_uuid = target_uuid
        return record

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
