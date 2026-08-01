import asyncio
import traceback
from datetime import datetime, timedelta

from contract.schemas.architecture import BrowsingRecord
from contract.schemas.common import ErrorResponse
from contract.schemas.get import ScraperGetRequest
from fastapi import APIRouter, Depends, HTTPException

from scraper.api.common import get_scraper
from scraper.core.schemas import BotSpottedError
from scraper.core.Scraper import Scraper

LIFESPAN_BUFFER_GET_REQUEST = 5  # seconds

router = APIRouter()


@router.post(
    "/get",
    description=(
        "Core function to scrape a web page. "
        "Can support spam calls and execute the requests sequentially, with no guarantee on the first one to resolve. "
    ),
    responses={
        409: {
            "model": ErrorResponse,
            "description": "No browser instance with given ID",
        },
        406: {
            "model": ErrorResponse,
            "description": "The target browser instance does not have sufficient lifespan",
        },
        423: {
            "model": ErrorResponse,
            "description": "The scraper is busy (likely terminating)",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {
            "model": ErrorResponse,
            "description": "The browser instance failed to retrieve the content successfully",
        },
    },
)
async def get(
    request: ScraperGetRequest, scraper: Scraper = Depends(get_scraper)
) -> BrowsingRecord:
    if scraper.restarting:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    if not await scraper.browser_exists(request.profile_uuid):
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance with id {request.profile_uuid}",
        )

    browser = scraper.browsers[request.profile_uuid]

    if browser.remaining_lifespan < timedelta(seconds=LIFESPAN_BUFFER_GET_REQUEST):
        raise HTTPException(
            status_code=406,
            detail=f"The browser instance with id {request.profile_uuid} does not have sufficient lifespan",
        )

    # browser_status = browser.status()
    # if browser_status != "idle":
    #     raise HTTPException(
    #         status_code=status.HTTP_423_LOCKED,
    #         detail=f"The browser instance is not available ({browser_status})",
    #     )

    try:
        return await scraper.scrape(request)
    except asyncio.CancelledError:
        raise HTTPException(
            status_code=503, detail="The task was cancelled by the scraper."
        )
    except BotSpottedError as e:
        raise HTTPException(status_code=503, detail=e.detail)
    except:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=traceback.format_exc())
