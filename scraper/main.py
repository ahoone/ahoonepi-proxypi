import asyncio
import sys
from contextlib import asynccontextmanager

from api.routes.available import router as available_router
from api.routes.get import router as get_router
from api.routes.get_scraper_state import router as get_scraper_state_router
from api.routes.health import router as health_router
from api.routes.kill import router as kill_router
from api.routes.new_instance import router as new_instance_router
from api.routes.stream import router as stream_router
from Config import Config
from core.Scraper import Scraper
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, "/plugins")
from middleware import add_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
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
)

add_middleware(app, Config.ALLOWED_NETWORKS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(available_router)
app.include_router(get_router)
app.include_router(get_scraper_state_router)
app.include_router(health_router)
app.include_router(kill_router)
app.include_router(new_instance_router)
app.include_router(stream_router)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #
