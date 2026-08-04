from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, DirectoryPath


class ProfileNotFoundError(Exception):
    pass


class RecordProfile(BaseModel):
    uuid: UUID
    name: str
    user_data_dir: DirectoryPath
    created_at: datetime
