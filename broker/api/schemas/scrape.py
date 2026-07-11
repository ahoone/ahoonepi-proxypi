import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from broker.Config import Config


class ScrapeRequest(BaseModel):
    url: HttpUrl | list[HttpUrl] = Field(
        description=(
            "Can be either an url or a list of urls. "
            "They will all get the same tag and expected_response_time. "
        ),
    )
    expected_response_time: datetime.datetime = Field(
        default_factory=datetime.datetime.now,
        description=(
            "Time you hope the response to be completed. "
            "As an isoformat string of <datetime.datetime>. "
            "By default, the timestamp of the request. "
        ),
    )
    tag: str = Field(
        description=(
            "Required to keep traces of who is requiring what, "
            "and group them as a common objective."
        ),
    )
    flag_lazy_loading: bool = Field(
        default=Config.TRIGGER_LAZY_LOADING_BY_DEFAULT,
        description=(
            "Flag transfered to the scraper. "
            "Triggers a logic that scrolls down and wait. "
        ),
    )


class ScrapeResponse(BaseModel):
    uuid: UUID | list[UUID]
