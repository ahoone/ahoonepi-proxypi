import traceback

from contract.config import config
from contract.schemas.common import ErrorResponse
from contract.schemas.new_instance import NewInstanceRequest, NewInstanceResponse
from fastapi import APIRouter, Body, Depends, HTTPException

from scraper.api.common import get_scraper
from scraper.core.models.Scraper import IdentifierInUse
from scraper.core.Scraper import Scraper

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
    request: NewInstanceRequest | None = Body(NewInstanceRequest()),
    scraper: Scraper = Depends(get_scraper),
) -> NewInstanceResponse:

    if scraper.restarting:
        raise HTTPException(
            status_code=423,
            detail="The scraper is restarting",
        )

    if len(scraper.browsers) > config.MAX_INSTANCES_PER_SCRAPER:
        raise HTTPException(
            status_code=409,
            detail=f"Already too many opened instances {config.MAX_INSTANCES_PER_SCRAPER}",
        )

    try:
        uuid = await scraper.new_instance(request)
        return NewInstanceResponse(profile_uuid=uuid)
    except IdentifierInUse:
        raise HTTPException(
            status_code=409,
            detail=f"Browser instance with id {request.profile_uuid} already exists",
        )
    except:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=traceback.format_exc())
