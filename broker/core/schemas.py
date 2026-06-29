import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class CollectRequest(BaseModel):
    uuid: UUID
    # flag to delete when retrieve ?


class GetRequest(BaseModel):
    url: str


class ScrapeRequest(BaseModel):
    """
    antwortzeit is the time you hope the response
    default is the time of receiving the request
    else is an isoformat string of datetime.datetime
    """

    url: HttpUrl
    antwortzeit: Optional[datetime.datetime] = Field(
        default_factory=datetime.datetime.now
    )
    tag: str


class ClearRequest(BaseModel):
    flag_clear_unassigned_targets: Optional[bool] = True
