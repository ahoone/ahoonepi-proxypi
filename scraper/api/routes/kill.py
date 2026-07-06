import traceback

from api.common import get_scraper
from common.schemas.kill import KillRequest
from core.Scraper import Scraper
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post(
    "/kill",
    description=(
        "Kill the target instance correctly cleaning its tasks and processes. "
        "Does not return if the killing was successfull, as ending the chromedriver process may take some time. "
    ),
)
async def kill(request: KillRequest, scraper: Scraper = Depends(get_scraper)):
    """ """
    if not scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance with id {request.instance_id}",
        )

    try:
        await scraper.kill(request.instance_id)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
