"""Cover caricata dall'utente sulle playlist di Cratory (manual/shazam).

`POST /api/playlists/{id}/artwork` salva l'immagine sotto `DATA_DIR/data/covers`
e punta `artwork_url` alla `GET` gemella; `DELETE` la toglie. Le playlist
sincronizzate tengono la cover della piattaforma: 409.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist
from app.services import playlist_artwork

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture()
def client_db(tmp_path, monkeypatch):
    monkeypatch.setattr(playlist_artwork, "covers_dir", lambda: tmp_path / "covers")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _manual(db, kind="manual"):
    pl = Playlist(platform="manual", name="Warm up", kind=kind)
    db.add(pl); db.commit()
    return pl


def _upload(client, pid, data=PNG, name="cover.png", ctype="image/png"):
    return client.post(f"/api/playlists/{pid}/artwork", files={"file": (name, data, ctype)})


def test_upload_salva_il_file_e_punta_artwork_url_alla_get(client_db, tmp_path):
    client, db = client_db
    pl = _manual(db)
    r = _upload(client, pl.id)
    assert r.status_code == 200, r.text
    url = r.json()["artwork_url"]
    assert url.startswith(f"/api/playlists/{pl.id}/artwork?v=")
    assert (tmp_path / "covers" / f"playlist-{pl.id}.png").read_bytes() == PNG
    got = client.get(f"/api/playlists/{pl.id}/artwork")
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    assert got.content == PNG


def test_un_nuovo_upload_sostituisce_il_precedente_e_cambia_la_versione(client_db, tmp_path):
    client, db = client_db
    pl = _manual(db)
    v1 = _upload(client, pl.id).json()["artwork_url"]
    v2 = _upload(client, pl.id, data=JPEG, name="cover.jpg", ctype="image/jpeg").json()["artwork_url"]
    assert v1 != v2  # cache-busting: l'URL cambia con l'immagine
    covers = sorted(p.name for p in (tmp_path / "covers").iterdir())
    assert covers == [f"playlist-{pl.id}.jpg"]  # il .png vecchio e' sparito
    assert client.get(f"/api/playlists/{pl.id}/artwork").headers["content-type"] == "image/jpeg"


def test_il_tipo_lo_decide_il_contenuto_non_il_content_type_dichiarato(client_db):
    client, db = client_db
    pl = _manual(db)
    # Un file di testo spacciato per PNG: rifiutato.
    r = _upload(client, pl.id, data=b"ciao sono un testo" + b"\x00" * 16, ctype="image/png")
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "unsupported_image_type"


def test_troppo_grande_413(client_db, monkeypatch):
    client, db = client_db
    monkeypatch.setattr(playlist_artwork, "MAX_BYTES", 64)
    pl = _manual(db)
    r = _upload(client, pl.id, data=PNG + b"\x00" * 100)
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "image_too_large"


def test_playlist_sincronizzata_409(client_db):
    client, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="S", kind="playlist",
                  artwork_url="https://i.scdn.co/x.jpg")
    db.add(pl); db.commit()
    r = _upload(client, pl.id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "playlist_artwork_not_editable"
    db.refresh(pl)
    assert pl.artwork_url == "https://i.scdn.co/x.jpg"


def test_shazam_e_di_cratory_quindi_si_puo(client_db):
    client, db = client_db
    pl = _manual(db, kind="shazam")
    assert _upload(client, pl.id).status_code == 200


def test_playlist_inesistente_404(client_db):
    client, _ = client_db
    assert _upload(client, 9999).status_code == 404
    assert client.get("/api/playlists/9999/artwork").status_code == 404
    assert client.delete("/api/playlists/9999/artwork").status_code == 404


def test_get_senza_cover_404(client_db):
    client, db = client_db
    pl = _manual(db)
    r = client.get(f"/api/playlists/{pl.id}/artwork")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "playlist_artwork_missing"


def test_delete_toglie_file_e_url(client_db, tmp_path):
    client, db = client_db
    pl = _manual(db)
    _upload(client, pl.id)
    r = client.delete(f"/api/playlists/{pl.id}/artwork")
    assert r.status_code == 200
    assert r.json()["artwork_url"] is None
    assert list((tmp_path / "covers").iterdir()) == []
    assert client.get(f"/api/playlists/{pl.id}/artwork").status_code == 404
    # Idempotente: togliere una cover che non c'e' non e' un errore.
    assert client.delete(f"/api/playlists/{pl.id}/artwork").status_code == 200


def test_cancellare_la_playlist_toglie_anche_la_cover(client_db, tmp_path):
    client, db = client_db
    pl = _manual(db)
    _upload(client, pl.id)
    assert client.delete(f"/api/playlists/{pl.id}").status_code == 200
    assert list((tmp_path / "covers").iterdir()) == []
