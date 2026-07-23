from uuid import UUID

from pydantic import BaseModel, Field

from contract.Config import Config


class NewInstanceRequest(BaseModel):
    profile_uuid: UUID | None = Field(default=None)

    instance_id: str = Field(default=Config.BROWSER_DEFAULT_ID)
    lifespan_in_seconds: int = Field(default=Config.BROWSER_DEFAULT_LIFESPAN)
    window_size: tuple[int, int] = Field(default=Config.BROWSER_DEFAULT_WINDOW)
