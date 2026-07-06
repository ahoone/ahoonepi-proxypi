import traceback
from typing import Dict

from api.common import get_scraper
from Config import Config
from core.Scraper import Scraper
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/available")
async def available(scraper: Scraper = Depends(get_scraper)) -> Dict[str, bool]:
    try:
        return {
            "available": len(scraper.browsers) < Config.MAX_INSTANCES_PER_SCRAPER,
        }
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
