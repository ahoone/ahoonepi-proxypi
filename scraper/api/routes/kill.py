import traceback

from api.common import get_scraper
from contract.schemas.common import ErrorResponse
from contract.schemas.kill import KillRequest
from core.Scraper import Scraper
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post(
    "/kill",
    status_code=204,
    description=(
        "Kill the target instance correctly cleaning its tasks and processes. "
        "Does not return if the killing was successfull, as ending the chromedriver process may take some time. "
    ),
    responses={
        423: {
            "model": ErrorResponse,
            "description": "The scraper is busy (likely terminating)",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def kill(request: KillRequest, scraper: Scraper = Depends(get_scraper)):
    if scraper.busy:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    if not await scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance with id {request.instance_id}",
        )

    try:
        await scraper.kill(request.instance_id)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
