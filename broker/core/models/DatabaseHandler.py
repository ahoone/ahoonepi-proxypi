import datetime
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class RecordTarget(BaseModel):
    id: UUID
    url: HttpUrl
    antwortzeit: datetime.datetime
    created_at: datetime.datetime
    tag: str
    flag_lazy_loading: bool
