import traceback

from fastapi import APIRouter, Depends, HTTPException

from broker.api.common import get_broker
from broker.core.Broker import Broker
from broker.core.models.Broker import BrokerModel
from contract.schemas.common import ErrorResponse

router = APIRouter()


@router.get(
    "/get_broker_state",
    description=(
        "Similar to the `get_scraper_state` for the scraper API, and includes the health fields. "
        "There could be a race in between the collection of running requests and unscraped targets, "
        "so the endpoint is supposed to deduplicate on `RecordTarget.uuid`. "
        "The running requests should be provided with more information (when started, on which node...). "
        "A query limit should be strongly enforced. "
    ),
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
async def get_broker_state(
    broker: Broker = Depends(get_broker),
) -> BrokerModel:
    try:
        return await broker.to_model()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
