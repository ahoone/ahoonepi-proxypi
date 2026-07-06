import os
import traceback
from typing import Any, Dict

from api.common import get_scraper
from common.Config import Config
from core.Scraper import Scraper
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/health", include_in_schema=False)
async def health(scraper: Scraper = Depends(get_scraper)) -> Dict[str, Any]:
    """
    Health function for unit tests.
    Also useful to get the availability of the scraper.
    """
    try:
        ram_total, ram_used, ram_free = map(
            int, os.popen("free -b").readlines()[1].split()[1:4]
        )

        return {
            "is_running_as_root": os.getuid() == 0,
            "can_create_browser": len(scraper.browsers)
            < Config.MAX_INSTANCES_PER_SCRAPER,
            "ram_specs": f"{ram_total // 1024**3}GiB",
            "ram_usage": f"{(100 * ram_used) // ram_total}%",
        }
    except Exception:
        raise HTTPException(status_code=500, detail=traceback.format_exc())
