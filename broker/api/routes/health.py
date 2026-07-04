import os

from api.common import get_broker
from Config import Config
from core.Broker import Broker
from core.NodeIdentifier import NodeIdentifier
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/health", include_in_schema=False)
async def health(broker: Broker = Depends(get_broker)):
    """
    Health function for unit tests.
    """
    return {
        "is_running_as_root": os.getuid() == 0,
        "broker_refresh_period": Config.REFRESH_PERIOD_BROKER,
        "broker_effective_refresh_period": broker.effective_refresh_period,
        "reachable_nodes": NodeIdentifier.reachable_nodes,
    }
