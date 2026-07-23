import datetime
from uuid import UUID

from pydantic import BaseModel


class ProfileNotFoundError(Exception):
    pass


class RecordProfile(BaseModel):
    profile_uuid: UUID
    profile_name: str
    created_at: datetime.datetime
