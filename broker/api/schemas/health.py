import os

from broker.Config import Config
from broker.core.NodeIdentifier import NodeIdentifier
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    is_running_as_root: bool = Field(default_factory=lambda: os.getuid() == 0)
    broker_refresh_period: float = Field(
        default=Config.REFRESH_PERIOD_BROKER, description="in seconds"
    )
    broker_effective_refresh_period: float = Field(description="in seconds")
    reachable_nodes: set[int] = Field(default_factory=lambda: set(NodeIdentifier.reachable_nodes))
