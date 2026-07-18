import datetime
from typing import Literal

from contract.schemas.architecture import BrowsingRecord
from pydantic import BaseModel


class BrowserImageModel(BaseModel):
    created_at: datetime.datetime
    expires_at: datetime.datetime
    browsing_history: list[BrowsingRecord]
    status: Literal["idle", "requesting", "spotted", "waiting"]
    score: float
