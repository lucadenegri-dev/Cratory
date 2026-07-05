"""Ricerca file audio locali per nome (servizio + endpoint)."""
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.file_search import search_audio_files


def _mk(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_match_case_insensitive_e_termini_in_and(tmp_path):
    _mk(tmp_path, "Artist - Amazing Title.mp3")
    _mk(tmp_path, "sub/artist - amazing title (remix).flac")
    _mk(tmp_path, "Other - Song.mp3")
    _mk(tmp_path, "Artist - Amazing Notes.txt")  # non audio: fuori

    hits = search_audio_files("amazing artist", roots=[("library", str(tmp_path))])
    names = {h["name"] for h in hits}
    assert names == {"Artist - Amazing Title.mp3", "artist - amazing title (remix).flac"}
    assert all(h["source"] == "library" for h in hits)
    assert all(h["size"] == 1 for h in hits)


def test_query_corta_o_vuota(tmp_path):
    _mk(tmp_path, "a.mp3")
    assert search_audio_files("", roots=[("library", str(tmp_path))]) == []
    assert search_audio_files("a", roots=[("library", str(tmp_path))]) == []


def test_cap_risultati(tmp_path):
    for i in range(60):
        _mk(tmp_path, f"track {i:02d}.mp3")
    assert len(search_audio_files("track", roots=[("library", str(tmp_path))], cap=50)) == 50


def test_endpoint_usa_le_radici_configurate(tmp_path, monkeypatch):
    _mk(tmp_path / "lib", "Deep Cut.mp3")
    _mk(tmp_path / "dl", "Deep Cut (edit).mp3")
    monkeypatch.setattr(settings, "library_root", str(tmp_path / "lib"))
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path / "dl"))

    r = TestClient(app).get("/api/files/search", params={"q": "deep cut"})
    assert r.status_code == 200
    rows = r.json()
    assert {x["source"] for x in rows} == {"library", "downloads"}
    assert all(x["format"] == "mp3" for x in rows)


def test_radici_non_configurate_o_inesistenti(monkeypatch):
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "slskd_download_dir", "/percorso/inesistente")
    r = TestClient(app).get("/api/files/search", params={"q": "qualcosa"})
    assert r.status_code == 200
    assert r.json() == []
