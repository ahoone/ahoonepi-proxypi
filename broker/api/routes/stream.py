import httpx
from api.common import get_broker
from Config import Config
from core.Broker import Broker
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

router = APIRouter()


@router.get("/stream/{hostname}/{instance_id}")
async def stream(hostname: str, instance_id: str, broker: Broker = Depends(get_broker)):
    scraper = broker.get_scraper_from_hostname(hostname)
    if not scraper:
        raise HTTPException(
            status_code=409, detail=f"No scraper with hostname {hostname}"
        )

    if instance_id not in scraper.browsers.keys():
        raise HTTPException(
            status_code=409,
            detail=f"No browser instance {instance_id} for scraper {hostname}",
        )

    url = f"http://{scraper.passport.vpn_address}:{Config.HTTP_PORT_SCRAPER}/stream/{instance_id}"

    client = httpx.AsyncClient()
    req = client.build_request("GET", url)
    response = await client.send(req, stream=True)

    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        headers=dict(response.headers),
        background=BackgroundTask(client.aclose),
    )
