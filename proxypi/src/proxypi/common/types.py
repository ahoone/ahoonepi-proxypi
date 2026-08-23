from datetime import timedelta
from ipaddress import IPv6Address
from typing import Annotated

from pydantic import BaseModel, Field

Port = Annotated[int, Field(ge=0, le=2**16 - 1)]


class SSHPingResponse(BaseModel):
    hostname: str
    node_id: int
    port: Port
    ipv6_address: IPv6Address
    timedelta_ssh_rtt: timedelta
    timedelta_internet: timedelta
