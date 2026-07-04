import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RecordRequest(BaseModel):
    """
    similar to core.BrowserImage.BrowserImageGetResult
    but enhanced with the target_uuid
    """

    target_uuid: UUID
    request_timestamp: datetime.datetime
    response_timestamp: datetime.datetime
    success: bool
    content: str


class Event(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    detail: str
    level: Literal["DEBUG", "INFO", "WARNING"]
