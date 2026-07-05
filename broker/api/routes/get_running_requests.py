import traceback
from typing import List
from uuid import UUID

from api.common import get_broker
from api.schemas.common import ErrorResponse
from core.Broker import Broker
from core.DatabaseHandler import DatabaseHandler
from core.models.DatabaseHandler import RecordTarget
from fastapi import APIRouter, Depends, HTTPException

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
) -> List[RecordTarget]:
    try:
        uuids: List[UUID] = await broker.get_running_tasks()
        if not uuids:
            return []
        return await DatabaseHandler.get_targets_from_uuids(uuids)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
