import datetime
from uuid import UUID

from Config import Config
from pydantic import BaseModel, Field


class CollectRequest(BaseModel):
    uuid: UUID
    # flag to delete when retrieve ?


class CollectRequestResponse(BaseModel):
    content: str


class ScrapeRequest(BaseModel):
    url: str
    antwortzeit: datetime.datetime = Field(
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


class ScrapeRequestResponse(BaseModel):
    uuid: UUID


class ClearRequest(BaseModel):
    flag_cancel_running_tasks: bool = Field(
        default=True,
        description=(
            "Should always be set to `True`. "
            "If you kill the browser without cancelling the task, the database would load it as a failed job. "
            "But you may just end with an improper state."
        ),
    )
    flag_kill_browsers: bool = Field(
        default=True,
        description="Kill all browsers instances on all nodes. ",
    )
    flag_clear_unassigned_targets: bool = Field(
        default=True,
        description=(
            "Makes any target previously registered as unactive target. "
            "But keeps them in the table, in case past requests are pointing to them. "
        ),
    )
