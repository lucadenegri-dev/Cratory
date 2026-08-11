import os
import time

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    # F1: un solo processo, un solo health check (app/main.py, non sotto
    # /api/organize): il main.py di Sortory che ne definiva uno proprio e'
    # stato assorbito in quello di Cratory.
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_sources_crud(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    with TestClient(app) as client:
        created = client.post("/api/organize/sources", json={"path": str(lib), "label": "Main"})
        assert created.status_code == 201
        root_id = created.json()["id"]
        assert created.json()["file_count"] == 0

        listed = client.get("/api/organize/sources").json()
        # F2: _fresh_db semina le due ScanRoot canoniche (id 1/2), quindi la
        # lista non è più esclusiva: verifica solo la presenza della sorgente
        # appena creata.
        created = next(r for r in listed if r["id"] == root_id)
        assert created["label"] == "Main"

        assert client.delete(f"/api/organize/sources/{root_id}").status_code == 204
        after = client.get("/api/organize/sources").json()
        assert all(r["id"] != root_id for r in after)


def test_delete_source_purges_thumbnail_caches(db, tmp_path, monkeypatch):
    """Gli id di AudioFile sono rowid semplici (niente AUTOINCREMENT): uno
    scan successivo può riassegnarli, quindi le cache thumbnail dei file
    cancellati con la sorgente vanno rimosse o un id riciclato rischia di
    servire la cover del file vecchio."""
    from app.core.config import settings
    from app.organize.models import AudioFile, ScanRoot
    from app.organize.services import cover_cache, thumbs

    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))

    lib = tmp_path / "lib"
    lib.mkdir()
    # id 3: 1 e 2 sono le ScanRoot canoniche seminate da _fresh_db (F2).
    db.add(ScanRoot(id=3, path=str(lib)))
    db.add(AudioFile(id=10, root_id=3, path=f"{lib}/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=True))
    db.add(AudioFile(id=11, root_id=3, path=f"{lib}/b.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.commit()

    with open(thumbs.thumb_path(10), "wb") as fh:
        fh.write(b"\xff\xd8thumb")
    with open(cover_cache.thumb_path(11), "wb") as fh:
        fh.write(b"\xff\xd8cover")

    with TestClient(app) as client:
        assert client.delete("/api/organize/sources/3").status_code == 204

    assert not os.path.exists(thumbs.thumb_path(10))
    assert not os.path.exists(cover_cache.thumb_path(11))


def test_sources_count_excludes_missing(db, tmp_path):
    from app.organize.models import AudioFile, ScanRoot

    lib = tmp_path / "lib"
    lib.mkdir()
    # id 3: 1 e 2 sono le ScanRoot canoniche seminate da _fresh_db (F2).
    db.add(ScanRoot(id=3, path=str(lib)))
    for i, status in enumerate(["present", "present", "missing", "missing", "missing"]):
        db.add(AudioFile(root_id=3, path=f"{lib}/{i}.mp3", ext="mp3", size_bytes=1,
                         hash_method="file", status=status, has_cover=False))
    db.commit()
    with TestClient(app) as client:
        row = next(r for r in client.get("/api/organize/sources").json() if r["id"] == 3)
        assert row["file_count"] == 2       # solo i presenti su disco
        assert row["missing_count"] == 3    # i mancanti restano visibili a parte


def test_add_source_rejects_missing_path():
    with TestClient(app) as client:
        resp = client.post("/api/organize/sources", json={"path": "/percorso/inesistente/xyz"})
        assert resp.status_code == 400


def test_scan_endpoint_end_to_end(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/organize/sources", json={"path": str(lib)}).json()["id"]
        started = client.post("/api/organize/scan", json={"root_ids": [root_id]})
        assert started.status_code == 200

        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/organize/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1
