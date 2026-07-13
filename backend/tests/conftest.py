import copy
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import Base  # noqa: E402
import app.models  # noqa: E402,F401 — registra tutte le tabelle su Base.metadata prima di create_all
from app.services import (  # noqa: E402
    audio_analysis_job, library_index_job, mix_identify_job, soulseek_download_job,
    streaming_import_job,
)

CAMELOT_KEYS = [
    "1A", "2A", "3A", "4A", "5A", "6A", "7A", "8A", "9A", "10A", "11A", "12A",
    "1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B",
]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seed_tracks(db):
    """Factory fixture: seed_tracks(n, with_metadata) → inserisce tracce Spotify sintetiche."""
    from app.models import Track

    def _seed(n: int = 30, with_metadata: bool = True):
        for i in range(n):
            db.add(Track(
                platform="spotify",
                spotify_id=f"spot{i:06d}",
                platform_track_id=f"spot{i:06d}",
                source_type="spotify",
                isrc=f"USABC{i:07d}",
                title=f"Track {i}" if with_metadata else None,
                artist=f"Artist {i % 5}" if with_metadata else None,
                year=None,
                duration_seconds=300 + (i % 60),
                bpm=128.0 + (i % 8),
                camelot_key=CAMELOT_KEYS[i % len(CAMELOT_KEYS)],
                status="ready_for_set",
                has_local_file=True,
            ))
        db.commit()

    return _seed


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """I test non parlano MAI con l'API Anthropic vera: la chiave del .env
    reale renderebbe attivo l'anello AI del genere (lento e a pagamento).
    I test dell'AI monkeypatchano suggest_genre/il client esplicitamente."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ai_api_key", "")


@pytest.fixture(autouse=True)
def _no_real_library_scan(monkeypatch):
    """Un test che istanzia TestClient(app) fa scattare il lifespan di app/main.py
    (ensure_schema +, se LIBRARY_ROOT e' configurato nel .env reale dello
    sviluppatore, library_index_job.start_job_if_due): senza questo guard un test
    HTTP-level innescherebbe una scansione VERA della libreria musicale sul disco
    e scriverebbe sul DB reale (data/djassistant.db) invece che sul DB isolato del
    test — lento (minuti su una libreria grande) e non isolato tra i test."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", "")


# I 5 job in background (analisi BPM/key, indicizzazione libreria, download
# Soulseek, identificazione mix Shazam, import/sync streaming) tengono lo stato
# in un dict globale di modulo (app locale mono-utente, niente sessione HTTP per
# il polling). Un test che lascia lo stato a "running" (es. i test della guardia
# doppio-avvio in test_job_double_start.py) contaminerebbe qualsiasi test
# successivo che legge job_state() o chiama start_job() aspettandosi lo stato
# iniziale "idle".
_JOB_STATE_MODULES = [
    audio_analysis_job, library_index_job, mix_identify_job, soulseek_download_job,
    streaming_import_job,
]
_PRISTINE_JOB_STATES = [copy.deepcopy(m._state) for m in _JOB_STATE_MODULES]


@pytest.fixture(autouse=True)
def _reset_job_states():
    """Ripristina lo stato pristino di ogni job PRIMA e DOPO ogni test: prima, in
    caso un test precedente l'abbia lasciato sporco senza passare da qui (ordine
    di esecuzione non garantito); dopo, per non contaminare il test successivo."""
    def _reset():
        for module, pristine in zip(_JOB_STATE_MODULES, _PRISTINE_JOB_STATES):
            module._state.clear()
            module._state.update(copy.deepcopy(pristine))

    _reset()
    yield
    _reset()
