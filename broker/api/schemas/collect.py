from uuid import UUID

from pydantic import BaseModel


class CollectRequest(BaseModel):
    uuid: UUID
    # flag to delete when retrieve ?


class CollectRequestResponse(BaseModel):
    content: str
