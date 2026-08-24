from datetime import timedelta
from ipaddress import IPv6Address
from typing import Annotated

from pydantic import BaseModel, Field

Port = Annotated[int, Field(ge=0, le=2**16 - 1)]


class SSHPingResponse(BaseModel):
    hostname: str
    node_id: int | None = None
    port: Port | None = None
    ipv6_address: IPv6Address
    timedelta_ssh_rtt: timedelta | None = None
    timedelta_internet: timedelta
