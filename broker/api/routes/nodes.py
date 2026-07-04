import traceback
from typing import List

from api.common import get_broker
from core.Broker import Broker
from core.models.ScraperImage import ScraperImageModel
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get(
    "/nodes",
    description=(
        "Displays information about the nodes and their scraper component. "
        "Endpoint used by the dashboard. "
    ),
)
async def nodes(broker: Broker = Depends(get_broker)) -> List[ScraperImageModel]:
    try:
        return broker.to_model()
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
