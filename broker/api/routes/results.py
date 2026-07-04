import traceback

from core.DatabaseHandler import DatabaseHandler
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/results")
async def results():
    try:
        return await DatabaseHandler.get_scraped_targets()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
