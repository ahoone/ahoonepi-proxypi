import traceback
from uuid import UUID

from contract.schemas.common import ErrorResponse
from fastapi import APIRouter, Depends, HTTPException

from broker.api.common import get_broker
from broker.core.Broker import Broker
from broker.core.DatabaseHandler import DatabaseHandler
from broker.core.models.DatabaseHandler import RecordTarget

router = APIRouter()


@router.get(
    "/get_running_requests",
    status_code=200,
    responses={
        200: {"description": "Found running requests"},
        204: {"description": "No running requests found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_running_requests(
    broker: Broker = Depends(get_broker),
) -> list[RecordTarget]:
    try:
        uuids: list[UUID] = await broker.get_running_tasks()
        if not uuids:
            return []
        return await DatabaseHandler.get_targets_from_uuids(uuids)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
