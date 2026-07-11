import traceback

from contract.schemas.common import ErrorResponse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from scraper.api.common import get_scraper
from scraper.core.Scraper import Scraper

router = APIRouter()


@router.get(
    "/stream/{instance_id}",
    status_code=200,
    responses={
        423: {
            "model": ErrorResponse,
            "description": "The scraper is busy (likely terminating)",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def stream(instance_id: str, scraper: Scraper = Depends(get_scraper)):
    if scraper.busy:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    if not await scraper.browser_exists(instance_id):
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance with id {instance_id}",
        )

    try:
        return StreamingResponse(
            scraper.browsers[instance_id].stream(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"X-Accel-Buffering": "no"},
        )
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=traceback.format_exc())
