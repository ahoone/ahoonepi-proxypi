from pydantic import BaseModel, Field


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
