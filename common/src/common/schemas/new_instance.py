from typing import List, Tuple

from pydantic import BaseModel, Field

from common.Config import Config


class NewInstanceRequest(BaseModel):
    instance_id: str = Field(default=Config.BROWSER_DEFAULT_ID)
    lifespan_in_seconds: int = Field(default=Config.BROWSER_DEFAULT_LIFESPAN)
    window_size: Tuple[int, int] | List[int] = Field(
        default=Config.BROWSER_DEFAULT_WINDOW
    )
