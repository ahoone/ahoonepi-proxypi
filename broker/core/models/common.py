from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detail: str
    level: Literal["DEBUG", "INFO", "WARNING"]
