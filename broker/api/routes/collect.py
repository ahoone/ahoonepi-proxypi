import traceback

from api.common import get_broker
from api.schemas.collect import CollectRequest, CollectRequestResponse
from api.schemas.common import ErrorResponse
from Config import Config
from core.Broker import Broker
from core.DatabaseHandler import DatabaseHandler
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get(
    "/collect",
    description=(
        "Returns the successful html content associated with the url. "
        "May return different codes depending on the status of the requests. "
    ),
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Given UUID is not known as a target",
        },
        425: {
            "model": ErrorResponse,
            "description": "The target is being processed or has yet to be processed",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def collect(
    request: CollectRequest,
    broker: Broker = Depends(get_broker),
) -> CollectRequestResponse:
    query = f"""
        SELECT 1
        FROM {Config.DB_TABLE_TARGETS}
        WHERE id = (?)
    """
    try:
        response = await DatabaseHandler.fetchone(query, (str(request.uuid),))
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
    if not response:
        raise HTTPException(
            status_code=404,
            detail=f"Given UUID {request.uuid} is not known as a target.",
        )

    try:
        response = await broker.get_running_tasks()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
    if request.uuid in response:
        raise HTTPException(
            status_code=425,
            detail="Processing the target.",
        )

    query = query = f"""
        SELECT *
        FROM {Config.DB_TABLE_REQUESTS}
        WHERE 1=1
            AND success = TRUE
            AND {Config.DB_TABLE_TARGETS}_id = '{request.uuid}'
        ORDER BY id ASC
    """
    try:
        response = await DatabaseHandler.fetchone(query)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
    if not response:
        raise HTTPException(
            status_code=425,
            detail="Target yet to be proceed.",
        )
    return CollectRequestResponse(content=response["content"])
