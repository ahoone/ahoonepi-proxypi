import asyncio
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import ipaddress
import nodriver as uc
import os
import random
import sys
from typing import List, Dict, Callable

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "SCRAPER" in NODE_ROLE, "The node should be a scraper to launch this image"


LIFESPAN_BROWSER = 1  # in hours
PAGE_LOADING_UNIFORM_RANGE = (2, 4)  # in seconds
PAGE_SCROLLING_UNIFORM_RANGE = (200, 400)  # 100 <=> height of the browser window
PERIOD_CLEANUP_LOOP = 300  # in seconds


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    # ipaddress.ip_network("10.0.0.0/24"),      # VPN network
    ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
    ipaddress.ip_network("172.16.0.0/12"),    # Docker bridge networks (for dev) (and includes 172.23.0.1 ie localnetwork)
    ipaddress.ip_network(
        "192.168.0.0/16"
    ),  # Docker compose networks (for the proxypi socket)
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
]


app = FastAPI(title="Scraper API", description="Scraper", version="1.0.0")


@app.get("/check-ip")
async def check_ip(request: Request):
    return await fast_api_ip_middleware.check_ip(request, ALLOWED_NETWORKS)


@app.middleware("http")
async def filter_ip_middleware(request: Request, call_next: Callable):
    return await fast_api_ip_middleware.filter_ip_middleware(
        request, call_next, ALLOWED_NETWORKS
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class BrowserInstance:

    def __init__(
        self,
        expiration_date: datetime.datetime = None,
    ) -> None:
        self.browser = None
        self.expiration_date = None
        self._initialized = False
        self.created_at = datetime.datetime.now()
        self.access_history: List[Dict] = []

    # __INIT__ CAN NOT BE ASYNC IN PYTHON
    async def initialize(self, expiration_date: datetime.datetime = None):
        """Initialize the browser (called once)"""
        self.expiration_date = expiration_date or (
            datetime.datetime.now() + datetime.timedelta(hours=LIFESPAN_BROWSER)
        )
        if not self._initialized:
            self.browser = await uc.start(
                headless=False,  # If headerless, Cloudflare spots us.
                browser_args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1920,1080",
                ],  # If images are blocked, Cloudflare spots us.
                sandbox=False,
            )
            self._initialized = True
        return self

    async def scrape(self, url: str) -> str:
        """Scrape a URL using the persistent browser"""
        if not self._initialized:
            await self.initialize()

        access_record = {
            "url": url,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "in_progress",
        }

        try:
            page = await self.browser.get(url)
            await page.sleep(random.uniform(*PAGE_LOADING_UNIFORM_RANGE))
            await page.scroll_down(random.randint(*PAGE_SCROLLING_UNIFORM_RANGE))
            html_content = await page.get_content()

            access_record["status"] = "success"
            access_record["content_length"] = len(html_content)
            access_record["completed_at"] = datetime.datetime.now().isoformat()

            self.access_history.append(access_record)
            return html_content

        except Exception as e:
            access_record["status"] = "failed"
            access_record["error"] = str(e)
            access_record["completed_at"] = datetime.datetime.now().isoformat()
            self.access_history.append(access_record)
            raise

    def close(self):
        """Explicitly close the browser"""
        if self.browser:
            self.browser.stop()
            self._initialized = False

    def is_expired(self) -> bool:
        """Check if this instance has expired"""
        return datetime.datetime.now() > self.expiration_date

    def get_stats(self) -> Dict:
        """Get statistics about this instance"""
        total_requests = len(self.access_history)
        successful_requests = sum(
            1 for record in self.access_history if record["status"] == "success"
        )
        failed_requests = sum(
            1 for record in self.access_history if record["status"] == "failed"
        )

        return {
            "created_at": self.created_at.isoformat(),
            "expiration_date": self.expiration_date.isoformat(),
            "is_expired": self.is_expired(),
            "is_initialized": self._initialized,
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "access_history": self.access_history,
        }


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


class BrowserInstancePool:

    def __init__(self):
        self.instances: dict[str, BrowserInstance] = {}

    async def get_or_create_instance(self, instance_id: str) -> BrowserInstance:
        """Get existing instance or create new one"""
        if instance_id not in self.instances:
            instance = BrowserInstance()
            await instance.initialize()
            self.instances[instance_id] = instance

        instance = self.instances[instance_id]

        if instance.is_expired():
            instance.close()
            instance = BrowserInstance()
            await instance.initialize()
            self.instances[instance_id] = instance

        return instance

    def cleanup_expired(self):
        """Remove and close expired instances"""
        expired_ids = [
            instance_id
            for instance_id, instance in self.instances.items()
            if instance.is_expired()
        ]
        for instance_id in expired_ids:
            self.instances[instance_id].close()
            del self.instances[instance_id]

    def get_all_stats(self) -> Dict:
        """Get stats for all instances"""
        return {
            instance_id: instance.get_stats()
            for instance_id, instance in self.instances.items()
        }


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


pool = BrowserInstancePool()


@app.post("/scrape")
async def scrape_endpoint(url: str, instance_id: str = "default"):
    """Scrape a URL using a persistent browser instance"""
    try:
        instance = await pool.get_or_create_instance(instance_id)
        content = await instance.scrape(url)
        return {
            "status": "success",
            "content": content,
            "instance_id": instance_id,
        }
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.post("/close-instance")
def close_instance(instance_id: str):
    """Manually close a browser instance"""
    try:
        if instance_id in pool.instances:
            stats = pool.instances[instance_id].get_stats()
            pool.instances[instance_id].close()
            del pool.instances[instance_id]
            return {
                "status": "closed",
                "instance_id": instance_id,
                "final_stats": stats,
            }
        return {"status": "not_found", "instance_id": instance_id}
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )


@app.get("/instances")
async def list_instances():
    """List all active instances with their access history"""
    return {
        "total_instances": len(pool.instances),
        "instances": pool.get_all_stats(),
    }


@app.get("/instance/{instance_id}")
async def get_instance_details(instance_id: str):
    """Get detailed information about a specific instance"""
    if instance_id not in pool.instances:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    return {
        "instance_id": instance_id,
        **pool.instances[instance_id].get_stats(),
    }


@app.get("/instance/{instance_id}/history")
async def get_instance_history(instance_id: str):
    """Get access history for a specific instance"""
    if instance_id not in pool.instances:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    return {
        "instance_id": instance_id,
        "access_history": pool.instances[instance_id].access_history,
    }


@app.get("/stats")
async def get_global_stats():
    """Get global statistics across all instances"""
    all_stats = pool.get_all_stats()

    total_requests = sum(stats["total_requests"] for stats in all_stats.values())
    total_successful = sum(stats["successful_requests"] for stats in all_stats.values())
    total_failed = sum(stats["failed_requests"] for stats in all_stats.values())

    return {
        "total_instances": len(pool.instances),
        "total_requests": total_requests,
        "successful_requests": total_successful,
        "failed_requests": total_failed,
        "instances": all_stats,
    }


@app.on_event("startup")
async def startup_event():
    """Cleanup expired instances regularly"""

    async def cleanup_loop():
        while True:
            await asyncio.sleep(PERIOD_CLEANUP_LOOP)
            await pool.cleanup_expired()

    asyncio.create_task(cleanup_loop())
