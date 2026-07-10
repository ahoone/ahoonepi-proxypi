import traceback

from fastapi import APIRouter, Depends, HTTPException

from broker.api.common import get_broker
from broker.core.Broker import Broker

router = APIRouter()


@router.get("/logger")
async def logger(broker: Broker = Depends(get_broker)):
    try:
        return broker.logger
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
