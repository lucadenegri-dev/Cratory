from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, setup_logging
from app.db import ensure_schema
from app.routers import imports, sets, spotify, tracks, transitions


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    ensure_schema()
    yield


app = FastAPI(title="DJ Assistant", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports.router)
app.include_router(tracks.router)
app.include_router(transitions.router)
app.include_router(sets.router)
app.include_router(spotify.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
