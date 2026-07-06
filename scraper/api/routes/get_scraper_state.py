import traceback

from api.common import get_scraper
from common.schemas.get_scraper_state import ScraperModel
from core.Scraper import Scraper
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get(
    "/browsers",
    description=(
        "Returns all the info you need for the broker. "
        "Be sure to check what is contained inside of `browsers.browsing_history`. "
        "The models should be updated so the `ScraperModel` is just a list if `BrowserModel`. "
        "(ie moving the `instance_id` from key to field)"
    ),
)
async def get_scraper_state(scraper: Scraper = Depends(get_scraper)) -> ScraperModel:
    try:
        return scraper.to_model()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
