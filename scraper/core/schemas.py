from typing import List, Tuple, Union

from Config import Config
from pydantic import BaseModel


class BotSpottedError(Exception):
    def __init__(self, html: str):
        self.html: str = html
        super().__init__("spotted by anti bot")


class NewInstanceRequest(BaseModel):
    instance_id: str = Config.BROWSER_DEFAULT_ID
    lifespan_in_seconds: int = Config.BROWSER_DEFAULT_LIFESPAN
    window_size: Union[List[int], Tuple[int, int]] = Config.BROWSER_DEFAULT_WINDOW


class KillRequest(BaseModel):
    instance_id: str


class GetRequest(BaseModel):
    instance_id: str
    url: str
    flag_lazy_loading: bool = Config.TRIGGER_LAZY_LOADING_BY_DEFAULT
