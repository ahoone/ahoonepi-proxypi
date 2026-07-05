import traceback
from typing import List

from core.DatabaseHandler import DatabaseHandler
from core.models.DatabaseHandler import RecordTarget
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/get_unscraped_targets")
async def get_unscraped_targets() -> List[RecordTarget]:
    try:
        return await DatabaseHandler.get_unscraped_targets()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
