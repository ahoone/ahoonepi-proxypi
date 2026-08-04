import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scraper.api.routes.close_browser import router as close_browser_router
from scraper.api.routes.get import router as get_router
from scraper.api.routes.get_scraper_state import router as get_scraper_state_router
from scraper.api.routes.new_instance import router as new_instance_router
from scraper.api.routes.stream import router as stream_router
from scraper.api.routes.terminate import router as terminate_router
from scraper.Config import Config
from scraper.core.DatabaseHandler import DatabaseHandler
from scraper.core.Scraper import Scraper

sys.path.insert(0, "/plugins")
from middleware import add_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)
logging.basicConfig(filename="/data/scraper.log", level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await DatabaseHandler.initialize()
    app.state.scraper = Scraper()
    bg_task = asyncio.create_task(app.state.scraper.background_update())
    yield
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    await app.state.scraper.terminate()


app = FastAPI(
    title="Scraper",
    lifespan=lifespan,
    docs_url=None,
    redoc_url="/docs",
)

add_middleware(app, Config.ALLOWED_NETWORKS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(get_router)
app.include_router(get_scraper_state_router)
app.include_router(close_browser_router)
app.include_router(new_instance_router)
app.include_router(stream_router)
app.include_router(terminate_router)

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #
