import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
# pydantic-settings carica .env dentro Settings (incluso ai_api_key, passato
# esplicito ai client Anthropic), ma non tocca l'os.environ di processo. Serve
# comunque per FPCALC, letto direttamente da os.environ in
# organize/integrations/acoustid.py.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, setup_logging
from app.db import ensure_schema
from app.organize.services import scan_job
from app.routers import (
    ai,
    analysis,
    discovery,
    dj_sets,
    download_queue,
    downloads,
    files,
    labels,
    pipeline,
    playlists,
    rekordbox,
    services,
    sets,
    setup,
    slskd,
    soundcloud,
    spotify,
    tracks,
    transitions,
    updates,
)
from app.routers import settings as settings_router
from app.organize.routers import (
    analyze as organize_analyze,
    apply as organize_apply,
    duplicates as organize_duplicates,
    files as organize_files,
    fingerprint as organize_fingerprint,
    genre_review as organize_genre_review,
    history as organize_history,
    issues as organize_issues,
    library as organize_library,
    plan as organize_plan,
    scan as organize_scan,
    settings as organize_settings,
)

logger = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # F2: un solo Base/engine. ensure_schema crea anche le tabelle Organize
    # (import differito di app.organize.models dentro app.db.ensure_schema).
    ensure_schema()
    # Carica gli override di config (Settings UI) nella cache runtime PRIMA di
    # leggerli: library_root & co. possono essere sovrascritti dal DB.
    from app.core import runtime_settings
    from app.db import SessionLocal
    with SessionLocal() as db:
        runtime_settings.load(db)
    # Disk-first: il disco È la libreria — riallineala all'avvio, ma non a ogni
    # reload di uvicorn: start_job_if_due salta se un run è finito da poco. Il job
    # è un thread daemon; con la scansione incrementale il costo è minimo.
    if runtime_settings.library_root():
        scan_job.start_job_if_due()
    # Coda download: gli item rimasti `running` da un riavvio tornano in coda,
    # e se c'e' lavoro il pool riparte da solo.
    from app.services import download_dispatcher
    download_dispatcher.boot()
    yield
    # E' un thread daemon: muore comunque col processo. Ma senza fermarlo qui
    # puo' svegliarsi durante lo shutdown, rivendicare un item (`running`) e
    # non finire mai di lavorarlo — lo si ferma esplicitamente, come i test
    # gia' fanno tra un test e l'altro (vedi conftest.py).
    download_dispatcher.stop_retry_loop()


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
app.include_router(ai.router)
app.include_router(discovery.router)
app.include_router(dj_sets.router)
app.include_router(services.router)
app.include_router(slskd.router)
app.include_router(downloads.router)
app.include_router(download_queue.router)
app.include_router(files.router)
app.include_router(pipeline.router)
app.include_router(rekordbox.router)
app.include_router(analysis.router)
app.include_router(soundcloud.router)
app.include_router(settings_router.router)
app.include_router(updates.router)
app.include_router(setup.router)

for _organize_router in (
    organize_scan, organize_analyze, organize_issues,
    organize_duplicates, organize_settings, organize_plan, organize_apply,
    organize_history, organize_library, organize_files, organize_fingerprint,
    organize_genre_review,
):
    app.include_router(_organize_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
