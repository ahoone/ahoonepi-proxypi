from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import IPv4Address
from typing import Annotated, Generic, ParamSpec, TypeVar, override

from pydantic import BaseModel, Field

from proxypi.common.config import config
from proxypi.common.constants import RANGE_PORTS

P = ParamSpec("P")
T = TypeVar("T")

AsyncFunc = Callable[P, Awaitable[T]]

DataModel = TypeVar("DataModel", bound=BaseModel)

PosInt = Annotated[int, Field(ge=1)]

# pydantic flavored, not compatible with typer
# NodeID = lighthouse + ProxyID
# ie a ProxyID included in NodeID
Port = Annotated[int, Field(ge=RANGE_PORTS[0], le=RANGE_PORTS[1])]
NodeID = Annotated[int, Field(ge=1, le=config.network_size - 1)]
ProxyID = Annotated[int, Field(ge=2, le=config.network_size - 1)]


def port_to_node_id(
    port: Port, *, ssh_network_base: int = config.ssh_network_base
) -> NodeID:
    return port - ssh_network_base + 2


def node_id_to_port(
    node_id: NodeID, *, ssh_network_base: int = config.ssh_network_base
) -> Port:
    if node_id == 1:
        raise ValueError("this action should not be performed on the lighthouse id")
    return node_id + ssh_network_base - 2


TTarget = TypeVar("TTarget", bound=IPv4Address | Port | None)


class CommandResponse(BaseModel, Generic[TTarget]):
    bash_command: str
    target: TTarget
    returncode: int
    stdout: str
    stderr: str
    duration: timedelta


@dataclass
class ExitCodeError(Exception):
    """
    Very similar to subproccess.CalledProcessError
    Considering using it here
    """

    bash_command: str
    host: IPv4Address | Port | None
    returncode: int
    stderr: str

    @override
    def __str__(self) -> str:
        return (
            f"Command `{self.bash_command}` failed on"
            + (f" {self.host}" if self.host else " localhost")
            + f" with exit code {self.returncode}"
            + (f":\n{self.stderr}" if self.stderr != "" else " (stderr is empty).")
        )
