from typing import List, Tuple, Union

from Config import Config
from pydantic import BaseModel


class BotSpottedError(Exception):
    def __init__(self, html: str):
        self.html: str = html
        super().__init__("spotted by anti bot")
