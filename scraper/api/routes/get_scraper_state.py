import traceback

from contract.schemas.architecture import ScraperModel
from contract.schemas.common import ErrorResponse
from fastapi import APIRouter, Depends, HTTPException

from scraper.api.common import get_scraper
from scraper.core.Scraper import Scraper

router = APIRouter()


@router.get(
    "/get_scraper_state",
    description=(
        "Returns all the info you need for the broker. "
        "Be sure to check what is contained inside of `browsers.browsing_history`. "
        "The models should be updated so the `ScraperModel` is just a list if `BrowserModel`. "
        "(ie moving the `instance_id` from key to field)"
    ),
    responses={
        423: {
            "model": ErrorResponse,
            "description": "The scraper is busy (likely terminating)",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_scraper_state(scraper: Scraper = Depends(get_scraper)) -> ScraperModel:
    if scraper.busy:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    try:
        return await scraper.to_model()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
