from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from contract.config import config


class NewInstanceRequest(BaseModel):
    profile_uuid: UUID | None = Field(default=None)
    profile_name: str | None = Field(
        default=None,
        description=(
            "This field will be omitted if the given `profile_uuid` already has a name in the database. "
            "Used primarly to give names to instances in tests. "
        ),
    )
    lifespan_in_seconds: int = Field(default=Config.BROWSER_DEFAULT_LIFESPAN)
    is_temporary: bool = Field(
        default=True,
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


class NewInstanceResponse(BaseModel):
    profile_uuid: UUID
