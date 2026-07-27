from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProfileNotFoundError(Exception):
    pass


class RecordProfile(BaseModel):
    uuid: UUID
    name: str
    created_at: datetime
