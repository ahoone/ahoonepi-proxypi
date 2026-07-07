import traceback
from typing import Optional

from api.common import get_broker
from api.schemas.clear import ClearRequest
from common.schemas.common import ErrorResponse
from core.Broker import Broker
from fastapi import APIRouter, Depends, HTTPException, Response, status

router = APIRouter()


@router.post(
    "/clear",
    status_code=status.HTTP_204_NO_CONTENT,
    description=(
        "Implements different flags to clear states handled by the broker without restarting the service. "
        "Makes the broker hibernate (skip its update cycle) until completed. "
        "An improvement would be to cancel tasks with a specified `tag`. "
    ),
    responses={
        204: {"description": "Broker successfully cleared"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def clear(
    request: Optional[ClearRequest], broker: Broker = Depends(get_broker)
) -> Response:
    try:
        await broker.clear(request)
        return Response(status_code=204)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
