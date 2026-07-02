import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, setup_logging
from app.db import ensure_schema
from app.routers import (
    ai,
    discovery,
    dj_sets,
    downloads,
    enrichment,
    labels,
    pipeline,
    playlists,
    services,
    sets,
    spotify,
    tracks,
    transitions,
)

logger = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    ensure_schema()
    yield


app = FastAPI(title="Cratory", version="0.9.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # frontend_origin puo' elencare piu' origini separate da virgola (dev 3000, preview 3001).
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000
        logger.exception("%s %s -> errore non gestito dopo %.0fms",
                         request.method, request.url.path, elapsed)
        raise
    elapsed = (time.perf_counter() - start) * 1000
    logger.info("%s %s -> %s (%.0fms)",
                request.method, request.url.path, response.status_code, elapsed)
    return response

app.include_router(tracks.router)
app.include_router(transitions.router)
app.include_router(sets.router)
app.include_router(playlists.router)
app.include_router(labels.router)
app.include_router(spotify.router)
app.include_router(enrichment.router)
app.include_router(ai.router)
app.include_router(discovery.router)
app.include_router(dj_sets.router)
app.include_router(services.router)
app.include_router(downloads.router)
app.include_router(pipeline.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
