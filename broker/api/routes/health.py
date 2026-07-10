import os

from fastapi import APIRouter, Depends

from broker.api.common import get_broker
from broker.api.schemas.health import HealthResponse
from broker.Config import Config
from broker.core.Broker import Broker
from broker.core.NodeIdentifier import NodeIdentifier

router = APIRouter()


@router.get("/health")
async def health(broker: Broker = Depends(get_broker)) -> HealthResponse:
    """
    Health function for unit tests.
    """
    return HealthResponse(
        is_running_as_root=os.getuid() == 0,
        broker_refresh_period=Config.REFRESH_PERIOD_BROKER,
        broker_effective_refresh_period=broker.effective_refresh_period,
        reachable_nodes=set(NodeIdentifier.reachable_nodes),
    )
