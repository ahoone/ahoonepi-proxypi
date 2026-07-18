import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from broker.core.models.DatabaseHandler import RecordTarget
from broker.core.models.ScraperImage import ScraperImageModel


class Event(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    detail: str
    level: Literal["DEBUG", "INFO", "WARNING"]


class BrokerModel(BaseModel):
    is_running_as_root: bool
    broker_refresh_period: float = Field(description="in seconds")
    broker_effective_refresh_period: float | None = Field(description="in seconds")
    nodes: list[ScraperImageModel]
    logs: list[Event]
    running_requests: list[RecordTarget]
    unscraped_targets: list[RecordTarget]
    scraped_targets: list[RecordTarget]
