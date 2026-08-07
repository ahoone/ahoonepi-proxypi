import asyncio
import logging
import traceback
from datetime import datetime
from uuid import UUID

import httpx
from contract.schemas.architecture import (
    BrowserModel,
    BrowserModelStatus,
    BrowsingRecord,
)
from contract.schemas.scrape import ScraperScrapeRequest

from broker.Config import Config
from broker.core.DatabaseHandler import DatabaseHandler
from broker.core.models.BrowserImage import BrowserImageModel
from broker.core.NodeIdentifier import NodeIdentifier

# this timeout is large because it accounts for lazy loading / others
TIMEOUT_HTTP_SCRAPING = 120  # seconds
TIMEOUT_HTTP_KILL = 10  # seconds

logger = logging.getLogger(__name__)


class BrowserImage:
    async def __initialize(
        self,
        passport: NodeIdentifier,
        browser_model: BrowserModel,
    ) -> None:
        self.uuid: UUID = browser_model.uuid
        self.name: str = browser_model.name
        self.passport: NodeIdentifier = passport
        self.created_at: datetime = browser_model.created_at
        self.expires_at: datetime = browser_model.expires_at
        self.browsing_history: list[
            BrowsingRecord
        ] = await DatabaseHandler.get_job_records_from_profile_uuid(self.uuid)
        self.status: BrowserModelStatus = browser_model.status
        self.score: float = browser_model.score

    @classmethod
    async def create(
        cls, passport: NodeIdentifier, browser_model: BrowserModel
    ) -> "BrowserImage":
        instance = cls()
        await instance.__initialize(passport, browser_model)
        return instance

    def to_model(self) -> BrowserImageModel:
        return BrowserImageModel(
            created_at=self.created_at,
            expires_at=self.expires_at,
            browsing_history=self.browsing_history,
            status=self.status,
            score=self.score,
        )

    async def scrape(
        self, target_request_uuid: UUID, payload: ScraperScrapeRequest
    ) -> BrowsingRecord:
        """
        Thread safe, but relies on `scraper.core.browser.get(...)`.
        Swallows `asyncio.CancelledError`.
        """
        try:
            response = await self.passport.client.post(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/scrape",
                json=payload.model_dump(mode="json"),
                timeout=TIMEOUT_HTTP_SCRAPING,
            )
        except httpx.TimeoutException:
            return BrowsingRecord(
                target_uuid=target_request_uuid,
                profile_uuid=self.uuid,
                url=payload.url,
                status="timeout",
                traceback=traceback.format_exc(),
            )
        except asyncio.CancelledError:
            return BrowsingRecord(
                target_uuid=target_request_uuid,
                profile_uuid=self.uuid,
                url=payload.url,
                status="aborted",
                traceback=traceback.format_exc(),
            )

        if response.status_code != 200:
            return BrowsingRecord(
                target_uuid=target_request_uuid,
                profile_uuid=self.uuid,
                url=payload.url,
                status="implementation_error",
                http_error_code=response.status_code,
                traceback=response.json()["detail"],
            )

        record = BrowsingRecord.model_validate(response.json())
        record.target_uuid = target_request_uuid
        return record

    async def close(self) -> bool:
        """
        Returns `True` if and only if the close request was successful.

        Returns:
            bool: Description.
        """
        try:
            response = await self.passport.client.post(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/close_browser",
                json={"profile_uuid": self.uuid},
                timeout=TIMEOUT_HTTP_SCRAPING,
            )
            return response.status_code == 204
        except httpx.TimeoutException:
            logger.error(
                f"Close request went timeout on {self.passport.vpn_address}:({self.uuid})"
            )
            return False
