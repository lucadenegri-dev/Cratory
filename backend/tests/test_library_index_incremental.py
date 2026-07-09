"""Indicizzazione incrementale: skip dei file invariati (path+mtime+size)."""
import pytest


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Stesso pattern di test_library_index.py: file finti, hash/tag deterministici."""
    from app.services import library_index as li

    hashes: dict[str, str] = {}
    tags: dict[str, dict] = {}

    def make(rel: str, *, digest: str, artist=None, title=None, isrc=None):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        hashes[str(p.resolve())] = digest
        tags[str(p.resolve())] = {
            "title": title, "artist": artist, "album": None, "year": None,
            "duration_seconds": 200, "isrc": isrc,
        }
        return p

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    return make, tmp_path


def test_own_salva_mtime_e_size(db, fake_audio):
    """L'aggancio memorizza mtime e size del file (base dell'incrementale)."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    p = make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)

    t = db.query(Track).filter(Track.audio_hash == "H1").one()
    stat = p.stat()
    assert t.local_mtime == stat.st_mtime
    assert t.local_size == stat.st_size


def test_file_invariato_niente_rehash(db, fake_audio, monkeypatch):
    """Secondo run senza modifiche: 0 hash calcolati, contatore unchanged, niente lost."""
    from app.services import library_index as li
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)  # primo run: aggancia

    calls = []
    original = li.audio_hash
    monkeypatch.setattr(li, "audio_hash", lambda p: calls.append(p) or original(p))
    report = index_library(db, root=root)  # secondo run: tutto invariato

    assert calls == []                      # nessun ri-hash
    assert report["unchanged"] == 1
    assert report["scanned"] == 1
    assert report["lost"] == 0              # il file "visto" non risulta perso
    assert report["matched"] == 0           # non ha rifatto il match


def test_file_modificato_viene_rielaborato(db, fake_audio):
    """mtime/size cambiati: il file rientra nel flusso completo."""
    import os
    from app.services.library_index import index_library

    make, root = fake_audio
    p = make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)

    p.write_bytes(b"xy")  # size cambia
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 10))
    report = index_library(db, root=root)

    assert report["unchanged"] == 0
    assert report["matched"] == 1  # riagganciato per hash


def test_duplicato_di_file_invariato_rilevato(db, fake_audio):
    """L'hash del file skippato entra in seen_digests: un duplicato nuovo si conta."""
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)

    make("House/A/A - T1 copia.mp3", digest="H1")  # stesso audio altrove
    report = index_library(db, root=root)

    assert report["unchanged"] == 1
    assert report["duplicates"] == 1


def test_archivio_non_matchato_niente_rehash(db, fake_audio, monkeypatch):
    """Un file nell'archivio che non corrisponde ad alcuna traccia NON deve essere
    ri-hashato a ogni run: era la causa dell'indicizzazione lenta a libreria ferma."""
    from app.services import library_index as li
    from app.services.library_index import index_library

    make, root = fake_audio
    make("lib/A - keep.mp3", digest="H1", artist="A", title="keep")          # libreria
    make("arch/X - orphan.mp3", digest="ARCH1", artist="X", title="orphan")  # archivio, non matcha
    lib, arch = root / "lib", root / "arch"
    index_library(db, root=lib, archive_root=arch)  # primo run: hash tutto

    calls: list[str] = []
    original = li.audio_hash
    monkeypatch.setattr(li, "audio_hash", lambda p: calls.append(str(p)) or original(p))
    report = index_library(db, root=lib, archive_root=arch)  # secondo run, tutto invariato

    assert calls == []             # niente ri-hash, né libreria né archivio
    assert report["unchanged"] >= 2


def test_auto_index_due_decision():
    """Il gate dell'auto-indicizzazione allo startup: salta se un run è finito da poco."""
    from datetime import datetime, timedelta, timezone
    from app.services.library_index_job import _auto_index_due

    now = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    assert _auto_index_due(None, now) is True                                    # mai indicizzato
    assert _auto_index_due((now - timedelta(minutes=3)).isoformat(), now) is False   # troppo recente
    assert _auto_index_due((now - timedelta(minutes=30)).isoformat(), now) is True   # abbastanza vecchio
    assert _auto_index_due("non-una-data", now) is True                          # valore corrotto: procedi
