from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    is_running_as_root: bool
    broker_refresh_period: float = Field(description="in seconds")
    broker_effective_refresh_period: float = Field(description="in seconds")
    reachable_nodes: set[int]
