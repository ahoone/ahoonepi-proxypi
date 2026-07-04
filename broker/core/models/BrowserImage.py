import datetime
from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class BrowserImageGet(BaseModel):
    id: UUID
    url: HttpUrl
    flag_lazy_loading: bool


class BrowserImageGetResult(BaseModel):
    request_timestamp: datetime.datetime
    response_timestamp: datetime.datetime
    success: bool
    content: str


class BrowserImageModel(BaseModel):
    created_at: datetime.datetime
    expires_at: datetime.datetime
    browsing_history: List[str]
    status: Literal["idle", "requesting", "spotted", "waiting"]
    score: float
