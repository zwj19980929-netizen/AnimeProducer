"""AnimeMatrix - AI-powered Anime Production Pipeline."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import api_test, assets, books, chapters, episodes, jobs, projects, ws, auth, lora
from api.websocket import manager as ws_manager
from config import settings
from core.database import init_db
from core.errors import AnimeMatrixError
from core.metrics import get_metrics, get_metrics_content_type

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    # Start WebSocket Redis listener
    logger.info("Starting WebSocket listener...")
    await ws_manager.start_listener()
    logger.info("WebSocket listener started")

    yield

    # Stop WebSocket Redis listener
    logger.info("Stopping WebSocket listener...")
    await ws_manager.stop_listener()
    logger.info("Shutting down AnimeMatrix...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.API_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(AnimeMatrixError)
async def animematrix_error_handler(request: Request, exc: AnimeMatrixError):
    return JSONResponse(
        status_code=400,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
        },
    )


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(
        f"request_id={request_id} path={request.url.path} "
        f"method={request.method} duration={duration:.3f}s status={response.status_code}"
    )

    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type()
    )


@app.get("/api/v1/info")
def api_info():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.API_VERSION,
        "debug": settings.DEBUG,
    }


app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(chapters.router, prefix="/api/v1/projects/{project_id}/chapters", tags=["chapters"])
app.include_router(episodes.router, prefix="/api/v1/projects/{project_id}/episodes", tags=["episodes"])
app.include_router(books.router, prefix="/api/v1/projects/{project_id}/book", tags=["books"])
app.include_router(assets.router, prefix="/api/v1/assets", tags=["assets"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(lora.router, prefix="/api/v1/lora", tags=["lora"])
app.include_router(api_test.router, prefix="/api/v1/api-test", tags=["api-test"])
app.include_router(ws.router, prefix="/ws", tags=["websocket"])

app.mount("/assets", StaticFiles(directory=settings.ASSETS_DIR), name="assets")
