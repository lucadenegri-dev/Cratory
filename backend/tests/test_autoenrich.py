"""Auto-enrichment: parte da solo per le tracce nuove (download, indice)."""


def test_report_indice_contiene_created_ids(db, tmp_path, monkeypatch):
    from app.services import library_index as li
    from app.services.library_index import index_library

    p = tmp_path / "Libreria" / "A - Nuova.mp3"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    monkeypatch.setattr(li, "audio_hash", lambda _: "H-NEW")
    monkeypatch.setattr(li, "read_tags", lambda _: {
        "title": "Nuova", "artist": "A", "album": None, "year": None,
        "duration_seconds": 200, "isrc": None, "genre": None})
    monkeypatch.setattr(li, "read_audio_quality", lambda _: {"format": "mp3", "bitrate": 320})

    report = index_library(db, root=tmp_path / "Libreria")
    assert report["created"] == 1
    assert len(report["created_ids"]) == 1


def test_job_indice_lancia_autoenrich(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.services import library_index_job

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(library_index_job, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(settings, "archive_root", "")
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())

    from app.services import enrichment_job
    calls = []
    monkeypatch.setattr(enrichment_job, "start_job",
                        lambda **kw: calls.append(kw) or {})
    # cartella vuota: nessuna traccia creata => niente enrich
    library_index_job.start_job()
    assert calls == []
    # una traccia nuova su disco => l'enrichment parte con i suoi id
    p = tmp_path / "A - Nuova.mp3"
    p.write_bytes(b"x")
    from app.services import library_index as li
    monkeypatch.setattr(li, "audio_hash", lambda _: "H-NEW")
    monkeypatch.setattr(li, "read_tags", lambda _: {
        "title": "Nuova", "artist": "A", "album": None, "year": None,
        "duration_seconds": 200, "isrc": None, "genre": None})
    monkeypatch.setattr(li, "read_audio_quality", lambda _: {"format": "mp3", "bitrate": 320})
    library_index_job.start_job()
    assert len(calls) == 1 and len(calls[0]["track_ids"]) == 1
