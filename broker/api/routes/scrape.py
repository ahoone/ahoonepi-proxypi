import traceback

from contract.schemas.common import ErrorResponse
from fastapi import APIRouter, HTTPException

from broker.api.schemas.scrape import ScrapeRequest, ScrapeResponse
from broker.core.DatabaseHandler import DatabaseHandler

router = APIRouter()


@router.post(
    "/scrape",
    description=(
        "Main method of getting the broker to scrape an url. "
        "The request will be loaded in the database and the broker will plan it. "
        "This endpoint should be used with `get.collect`. "
        "One improvment would be to add an expected time of collect. "
    ),
    status_code=202,
    responses={500: {"model": ErrorResponse, "description": "Internal server error"}},
)
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    try:
        return await DatabaseHandler.insert_scrape_request(request)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
