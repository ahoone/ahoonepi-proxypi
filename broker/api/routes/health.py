from fastapi import APIRouter, Depends

from broker.api.common import get_broker
from broker.api.schemas.health import HealthResponse
from broker.core.Broker import Broker

router = APIRouter()


@router.get("/health")
async def health(broker: Broker = Depends(get_broker)) -> HealthResponse:
    """
    Health function for unit tests.
    """
    return HealthResponse(
        broker_effective_refresh_period=broker.effective_refresh_period
    )
