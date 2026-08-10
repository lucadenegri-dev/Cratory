"""Entrypoint FastAPI di Sortory."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Carica backend/.env in os.environ: serve all'SDK Anthropic, che legge
# ANTHROPIC_API_KEY da os.environ. La key non ha il prefisso DJORG_, quindi
# pydantic-settings non la carica. override=False: non sovrascrive l'ambiente.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.db import ensure_schema  # noqa: E402
from app.routers import (  # noqa: E402
    analyze, apply, duplicates, files, fingerprint, genre_review, history, issues,
    library, picker, plan, providers, scan, settings, sources,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(title="Sortory", lifespan=lifespan)

# Tool locale: il frontend Next gira su un'altra porta (es. localhost:3000) e
# chiama l'API cross-origin. Consenti qualunque porta su localhost/127.0.0.1.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sources.router)
app.include_router(scan.router)
app.include_router(analyze.router)
app.include_router(issues.router)
app.include_router(duplicates.router)
app.include_router(settings.router)
app.include_router(plan.router)
app.include_router(apply.router)
app.include_router(history.router)
app.include_router(library.router)
app.include_router(files.router)
app.include_router(fingerprint.router)
app.include_router(providers.router)
app.include_router(picker.router)
app.include_router(genre_review.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
