import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class RecordTarget(BaseModel):
    id: UUID
    url: HttpUrl
    antwortzeit: datetime.datetime
    created_at: datetime.datetime
    tag: str
    flag_lazy_loading: bool
    is_running: Optional[bool] = Field(default=None)
