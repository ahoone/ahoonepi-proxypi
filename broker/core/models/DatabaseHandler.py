from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from broker.Config import Config


class RecordTarget(BaseModel):
    uuid: UUID
    url: HttpUrl
    expected_response_time: datetime
    created_at: datetime
    tag: str
    flag_lazy_loading: bool = Field(default=Config.TRIGGER_LAZY_LOADING_BY_DEFAULT)
