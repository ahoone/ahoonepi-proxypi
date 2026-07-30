from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str
    level: Literal["DEBUG", "INFO", "WARNING"]
