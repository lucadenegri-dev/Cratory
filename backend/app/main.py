"""Entrypoint FastAPI di DjOrganizer."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import ensure_schema
from app.routers import analyze, scan, sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(title="DjOrganizer", lifespan=lifespan)
app.include_router(sources.router)
app.include_router(scan.router)
app.include_router(analyze.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
