from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from contract.Config import Config


class NewInstanceRequest(BaseModel):
    profile_uuid: UUID | None = None
    lifespan_in_seconds: int = Field(default=Config.BROWSER_DEFAULT_LIFESPAN)
    is_temporary: bool = Field(
        default=False,
        description=(
            "If set to `True`, a new UUID will be generated and used just one time. "
            "In that case, the field `profile_uuid` must be empty. "
        ),
    )

    @model_validator(mode="after")
    def validate_is_temporary_option(self) -> "NewInstanceRequest":
        if self.is_temporary and self.profile_uuid is not None:
            raise ValueError(
                "`profile_uuid` must not be provided when `is_temporary=True`"
            )
        return self
