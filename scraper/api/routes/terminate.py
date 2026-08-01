import traceback

from contract.schemas.common import ErrorResponse
from fastapi import APIRouter, Depends, HTTPException

from scraper.api.common import get_scraper
from scraper.core.Scraper import Scraper

router = APIRouter()


@router.post(
    "/terminate",
    status_code=204,
    description=(
        "Kill all the instances. "
        "Does not return if the killing was successfull, as ending the chromedriver process may take some time. "
    ),
    responses={
        204: {"description": "The terminate method was initiated"},
        423: {
            "model": ErrorResponse,
            "description": "The scraper is busy (likely terminating)",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def terminate(scraper: Scraper = Depends(get_scraper)):
    if scraper.restarting:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    try:
        await scraper.terminate()
    except:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=traceback.format_exc())
