import traceback

from api.common import get_broker
from core.Broker import Broker
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/logger")
async def logger(broker: Broker = Depends(get_broker)):
    try:
        return broker.logger
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
