import traceback

from fastapi import APIRouter, HTTPException

from broker.core.DatabaseHandler import DatabaseHandler
from broker.core.models.DatabaseHandler import RecordTarget

router = APIRouter()


@router.get("/get_unscraped_targets")
async def get_unscraped_targets() -> list[RecordTarget]:
    try:
        return await DatabaseHandler.get_unscraped_targets()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
