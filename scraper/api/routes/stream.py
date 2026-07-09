import traceback

from api.common import get_scraper
from contract.schemas.common import ErrorResponse
from core.Scraper import Scraper
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

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
        raise HTTPException(status_code=500, detail=traceback.format_exc())
