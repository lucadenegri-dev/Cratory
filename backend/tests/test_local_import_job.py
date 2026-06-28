"""Job di import locale: stato e contatori dopo l'esecuzione sincrona del corpo."""

import math
import struct
import wave

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services import local_import_job


def _write_wav(path, *, freq: int = 440, secs: float = 0.4, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        ))


@pytest.fixture()
def patch_session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(local_import_job, "SessionLocal", TestSession)
    # niente provider di enrichment nei test: rendi l'auto-enrichment un no-op
    monkeypatch.setattr(local_import_job, "_autoenrich", lambda pid: None)
    return TestSession


def test_run_job_popola_stato(patch_session, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _write_wav(tmp_path / "b.wav", freq=660)
    local_import_job._run_job(str(tmp_path), "Crate")
    st = local_import_job.job_state()
    assert st["status"] == "done"
    assert st["total"] == 2
    assert st["created"] == 2
    assert st["processed"] == 2
    assert st["playlist_id"] is not None


def test_run_job_cartella_vuota(patch_session, tmp_path):
    local_import_job._run_job(str(tmp_path), "Vuota")
    st = local_import_job.job_state()
    assert st["status"] == "done"
    assert st["total"] == 0
    assert st["playlist_id"] is None
