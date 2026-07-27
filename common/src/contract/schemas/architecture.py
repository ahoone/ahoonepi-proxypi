from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, computed_field


class BrowsingRecord(BaseModel):
    """Safe to be exported to SQLite."""

    profile_uuid: UUID | None = None
    target_uuid: UUID | None = None
    url: HttpUrl
    status: (
        Literal[
            "aborted", "blocked", "failed", "timeout", "success", "implementation_error"
        ]
        | None
    ) = Field(
        default=None,
        description=(
            "aborted: task was cancelled either by the broker or the scraper. "
            "blocked: content was detected as a cloudflare firewall. "
            "failed: zendriver failed to move the tab or get the content. "
            "timeout: the transaction was stopped by the broker. "
            "implementation_error: the scraper api did not return a 200. "
        ),
    )
    tab_state: Literal["complete", "interactive", "loading"] | None = None
    html: str | None = None
    timestamp: datetime | None = Field(
        default=None, description=("Set by the scraper. Completed when the task ends. ")
    )

    timedelta_driver_get: float | None = None
    timedelta_smart_wait: float | None = None
    timedelta_search_cf_challenge: float | None = None
    timedelta_resolve_cf_challenge: float | None = None
    timedelta_check_cf_blocking_content: float | None = None
    timedelta_lazy_loading: float | None = None
    timedelta_get_content: float | None = None

    traceback: str | None = None
    http_error_code: int | None = None

    @computed_field
    @property
    def success(self) -> bool | None:
        if not self.status:
            return None
        return self.status == "success"


class ProfileModel(BaseModel):
    uuid: UUID
    name: str
    created_at: datetime


BrowserModelStatus = Literal[
    "closed",
    "closing",
    "requesting",
    "recovering",
    "idle",
]


class BrowserModel(BaseModel):
    profile: ProfileModel
    window_size: tuple[int, int]
    display: str
    created_at: datetime
    expires_at: datetime
    remaining_lifespan: timedelta
    status: BrowserModelStatus
    score: float


class ScraperModel(BaseModel):
    is_running_as_root: bool
    can_create_browser: bool
    ram_specs: str
    ram_usage: str
    browsers: dict[UUID, BrowserModel]
