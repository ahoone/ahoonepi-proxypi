import traceback

from api.common import get_scraper
from contract.Config import Config
from contract.schemas.common import ErrorResponse
from contract.schemas.new_instance import NewInstanceRequest
from core.Scraper import Scraper
from fastapi import APIRouter, Body, Depends, HTTPException

router = APIRouter()


@router.post(
    "/new-instance",
    status_code=201,
    description=(
        "Creates a new instances performing checks on its id and on the number of running instances. "
        "This request spawns processes and therefore can take time to complete. "
    ),
    responses={
        423: {
            "model": ErrorResponse,
            "description": "The scraper is busy (likely terminating)",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def new_instance(
    request: NewInstanceRequest = Body(default_factory=NewInstanceRequest),
    scraper: Scraper = Depends(get_scraper),
) -> None:
    if scraper.busy:
        raise HTTPException(
            status_code=423,
            detail="The scraper is busy",
        )

    if await scraper.browser_exists(request.instance_id):
        raise HTTPException(
            status_code=409,
            detail=f"Browser instance with id {request.instance_id} already exists",
        )

    if len(scraper.browsers) > Config.MAX_INSTANCES_PER_SCRAPER:
        raise HTTPException(
            status_code=409,
            detail=f"Already too many opened instances {Config.MAX_INSTANCES_PER_SCRAPER}",
        )

    try:
        await scraper.new_instance(request)
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
