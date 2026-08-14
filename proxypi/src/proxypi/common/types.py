from typing import Annotated

from pydantic import Field

Port = Annotated[int, Field(ge=0, le=2**16 - 1)]
