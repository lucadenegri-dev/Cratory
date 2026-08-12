import os
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

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
        # Radici canoniche seminate da _fresh_db: vedi conftest.SEEDED_SCAN_ROOT_IDS.
        row = next(r for r in listed if r["id"] == root_id)
        assert row["label"] == "Main"

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
    # ScanRoot id >= 3: 1 e 2 sono le canoniche (conftest.SEEDED_SCAN_ROOT_IDS).
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
    # ScanRoot id >= 3: 1 e 2 sono le canoniche (conftest.SEEDED_SCAN_ROOT_IDS).
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


def test_scan_endpoint_end_to_end(tmp_path, copy_fixture, monkeypatch):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        # Dopo l'avvio (guardia _no_real_library_scan intatta durante il
        # lifespan): scan_job deriva ora le radici da roots.radici(), che deve
        # vedere `lib` come LIBRARY_ROOT per adottare la sorgente appena creata.
        from app.core.config import settings
        monkeypatch.setattr(settings, "library_root", str(lib))
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


def test_delete_source_purges_derived_rows(db, tmp_path):
    """Issue/DupMember/DupGroup puntano ad audio_file con FK grezze (niente
    relationship(), niente ondelete): con foreign_keys=ON (F2) la delete della
    sorgente deve toglierle di mezzo a mano, o va in IntegrityError. Sono
    derivate (un nuovo scan le rigenera), a differenza di plan_op/undo_journal."""
    from app.organize.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot

    lib = tmp_path / "lib"
    lib.mkdir()
    # ScanRoot id >= 3: 1 e 2 sono le canoniche (conftest.SEEDED_SCAN_ROOT_IDS).
    db.add(ScanRoot(id=3, path=str(lib)))
    db.add(AudioFile(id=10, root_id=3, path=f"{lib}/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=11, root_id=3, path=f"{lib}/b.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.flush()
    db.add(Issue(file_id=10, type="tag_missing", field="artist", severity="warn",
                 detail="missing artist"))
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=10, signature="s"))
    db.add(DupMember(group_id=1, file_id=10, action="keep"))
    db.add(DupMember(group_id=1, file_id=11, action="remove"))
    db.commit()

    with TestClient(app) as client:
        assert client.delete("/api/organize/sources/3").status_code == 204

    db.expire_all()
    assert db.scalars(select(Issue)).all() == []
    assert db.scalars(select(DupMember)).all() == []
    assert db.scalars(select(DupGroup)).all() == []
    assert db.scalars(select(AudioFile).where(AudioFile.root_id == 3)).all() == []
    assert db.get(ScanRoot, 3) is None


def test_delete_source_rejects_when_plan_op_exists(db, tmp_path):
    """Un file con storia in plan_op (un apply già eseguito) blocca la delete
    della sorgente: quella storia è la reversibilità che il progetto considera
    irrinunciabile, non va persa come effetto collaterale di 'rimuovi radice'."""
    from app.organize.models import AudioFile, Plan, PlanOp, ScanRoot

    lib = tmp_path / "lib"
    lib.mkdir()
    db.add(ScanRoot(id=3, path=str(lib)))
    db.add(AudioFile(id=10, root_id=3, path=f"{lib}/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.flush()
    db.add(Plan(id=1, status="applied", rules_json={}))
    db.flush()
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=10,
                  before_json={"path": "a"}, after_json={"path": "b"}, status="done"))
    db.commit()

    with TestClient(app) as client:
        resp = client.delete("/api/organize/sources/3")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "source_has_run_history"

    db.expire_all()
    assert db.get(ScanRoot, 3) is not None
    assert db.scalars(select(AudioFile).where(AudioFile.id == 10)).first() is not None
    assert db.scalars(select(PlanOp).where(PlanOp.file_id == 10)).first() is not None


def test_delete_source_allows_when_only_draft_plan_op_exists(db, tmp_path):
    """Un piano draft (quello che la pagina Piano tiene sempre pronto per la
    preview) referenzia plan_op per ogni file: non è run history, è
    usa-e-getta (create_plan lo ricrea da zero a ogni chiamata). La delete
    della sorgente deve passare e le sue plan_op devono sparire con essa,
    altrimenti la FK plan_op.file_id scatterebbe sulla delete di audio_file."""
    from app.organize.models import AudioFile, Plan, PlanOp, ScanRoot

    lib = tmp_path / "lib"
    lib.mkdir()
    db.add(ScanRoot(id=3, path=str(lib)))
    db.add(AudioFile(id=10, root_id=3, path=f"{lib}/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.flush()
    db.add(Plan(id=1, status="draft", rules_json={}))
    db.flush()
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=10,
                  before_json={"path": "a"}, after_json={"path": "b"}, status="pending"))
    db.commit()

    with TestClient(app) as client:
        resp = client.delete("/api/organize/sources/3")
        assert resp.status_code == 204

    db.expire_all()
    assert db.get(ScanRoot, 3) is None
    assert db.scalars(select(AudioFile).where(AudioFile.id == 10)).first() is None
    assert db.scalars(select(PlanOp).where(PlanOp.file_id == 10)).first() is None


def test_delete_source_rejects_when_undo_journal_exists(db, tmp_path):
    """Stesso rifiuto se il file compare solo nell'undo_journal (senza righe
    ancora in plan_op, es. plan_op già rimosso a valle): la storia dell'undo
    resta il criterio, non solo la presenza di un piano."""
    from app.organize.models import AudioFile, Plan, ScanRoot, UndoJournal

    lib = tmp_path / "lib"
    lib.mkdir()
    db.add(ScanRoot(id=3, path=str(lib)))
    db.add(AudioFile(id=10, root_id=3, path=f"{lib}/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.flush()
    db.add(Plan(id=1, status="applied", rules_json={}))
    db.flush()
    db.add(UndoJournal(run_id=1, op_seq=0, kind="MOVE", file_id=10,
                        from_path="a", to_path="b"))
    db.commit()

    with TestClient(app) as client:
        resp = client.delete("/api/organize/sources/3")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "source_has_run_history"

    db.expire_all()
    assert db.get(ScanRoot, 3) is not None
    assert db.scalars(select(AudioFile).where(AudioFile.id == 10)).first() is not None
    assert db.scalars(select(UndoJournal).where(UndoJournal.file_id == 10)).first() is not None
