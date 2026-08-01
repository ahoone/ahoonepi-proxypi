import traceback
from uuid import UUID

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
async def stream(profile_uuid: UUID, scraper: Scraper = Depends(get_scraper)):
    if scraper.restarting:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    if not await scraper.browser_exists(profile_uuid):
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance with id {profile_uuid}",
        )

    try:
        return StreamingResponse(
            scraper.browsers[profile_uuid].stream(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"X-Accel-Buffering": "no"},
        )
    except:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=traceback.format_exc())
