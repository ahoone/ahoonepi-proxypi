import asyncio
import sys
from contextlib import asynccontextmanager

from api.routes.clear import router as clear_router
from api.routes.collect import router as collect_router
from api.routes.get_unscraped_targets import router as get_unscraped_targets_router
from api.routes.health import router as health_router
from api.routes.logger import router as logger_router
from api.routes.nodes import router as nodes_router
from api.routes.results import router as results_router
from api.routes.scrape import router as scrape_router
from api.routes.stream import router as stream_router
from Config import Config
from core.Broker import Broker
from core.DatabaseHandler import DatabaseHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

sys.path.insert(0, "/plugins")
from middleware import add_middleware

# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    await DatabaseHandler.initialize()
    app.state.broker = Broker()
    bg_task = asyncio.create_task(app.state.broker.background_update())

    yield

    bg_task.cancel()
    try:
        await bg_task
        await app.state.broker.terminate()
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Broker",
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

app.include_router(clear_router)
app.include_router(collect_router)
app.include_router(get_unscraped_targets_router)
app.include_router(health_router)
app.include_router(logger_router)
app.include_router(nodes_router)
app.include_router(results_router)
app.include_router(scrape_router)
app.include_router(stream_router)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse("dashboard.html")


@app.get("/dashboard.css", include_in_schema=False)
async def css():
    return FileResponse("dashboard.css")
