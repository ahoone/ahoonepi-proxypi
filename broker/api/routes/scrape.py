import traceback

from api.common import get_broker
from api.schemas.scrape import ScrapeRequest, ScrapeRequestResponse
from contract.schemas.common import ErrorResponse
from core.Broker import Broker
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter()


@router.post(
    "/scrape",
    description=(
        "Main method of getting the broker to scrape an url. "
        "The request will be loaded in the database and the broker will plan it. "
        "This endpoint should be used with `get.collect`. "
        "One improvment would be to add an expected time of collect. "
    ),
    status_code=status.HTTP_202_ACCEPTED,
    responses={500: {"model": ErrorResponse, "description": "Internal server error"}},
)
async def scrape(
    request: ScrapeRequest,
    broker: Broker = Depends(get_broker),
) -> ScrapeRequestResponse:
    try:
        return await broker.scrape(request)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
