from uuid import UUID

from pydantic import BaseModel, Field

from contract.Config import Config


class NewInstanceRequest(BaseModel):
    profile_uuid: UUID | None = Field(default=None)
    lifespan_in_seconds: int = Field(default=Config.BROWSER_DEFAULT_LIFESPAN)
    temporary_profile: bool = Field(
        default=True,
        description=(
            "If set to `True`, a new UUID will be generated and use just one time. "
            "However, if set to `True`, the field `profile_uuid` must be empty. "
        ),
    )
