import asyncio
import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Literal

import httpx
from Config import Config
from core.NodeIdentifier import NodeIdentifier

# this timeout is large because it accounts for lazy loading / others
TIMEOUT_HTTP_SCRAPING = 60  # seconds
TIMEOUT_HTTP_KILL = 10  # seconds


@dataclass
class BrowserImageGetResult:
    request_timestamp: float
    response_timestamp: float
    success: bool
    content: str


class BrowserImage:
    def __init__(
        self,
        instance_id: str,
        passport: NodeIdentifier,
        scraper_response: Dict[str, Any],
    ) -> None:
        self.instance_id: str = instance_id
        self.passport: NodeIdentifier = passport
        self.created_at: datetime.datetime = scraper_response["created_at"]
        self.expires_at: datetime.datetime = scraper_response["expires_at"]
        self.browsing_history: List[str] = []
        self.status: Literal["idle", "requesting", "spotted", "waiting"] = (
            scraper_response["status"]
        )
        self.score: float = scraper_response["score"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "browsing_history": self.browsing_history,
            "status": self.status,
            "score": self.score,
        }

    async def get(self, url: str) -> BrowserImageGetResult:
        """
        should be cancellable
        (therefore response_timestamp is not defined)
        """
        loop = asyncio.get_running_loop()
        request_timestamp = loop.time()
        try:
            response = await self.passport.client.post(
                f"http://{self.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/get",
                json={"instance_id": self.instance_id, "url": url},
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
