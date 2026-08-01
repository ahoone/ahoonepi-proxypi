from uuid import UUID

from pydantic import BaseModel


class CloseBrowserRequest(BaseModel):
    profile_uuid: UUID
