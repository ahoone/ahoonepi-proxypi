import traceback

from contract.schemas.common import ErrorResponse
from fastapi import APIRouter, Depends, HTTPException, Response, status

from broker.api.common import get_broker
from broker.api.schemas.clear import ClearRequest
from broker.core.Broker import Broker

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
    request: ClearRequest | None, broker: Broker = Depends(get_broker)
) -> Response:
    try:
        await broker.clear(request)
        return Response(status_code=204)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
