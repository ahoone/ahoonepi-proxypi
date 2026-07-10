import traceback

from fastapi import APIRouter, HTTPException

from broker.core.DatabaseHandler import DatabaseHandler

router = APIRouter()


@router.get("/results")
async def results():
    try:
        return await DatabaseHandler.get_scraped_targets()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
