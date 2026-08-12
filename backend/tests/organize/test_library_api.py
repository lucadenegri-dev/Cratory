from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot


def _seed_stats(db):
    db.add(ScanRoot(id=3, path="/m", label="M"))
    # location deliberatamente discriminante fra le righe: a.flac in library,
    # b.mp3 e c.mp3 in inbox, cosi' i test sul filtro ?location= fallirebbero
    # se il where venisse tolto (vedi Finding 1 della review F3b).
    db.add(AudioFile(id=1, root_id=3, path="/m/a.flac", ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     location="library"))
    db.add(AudioFile(id=2, root_id=3, path="/m/b.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     location="inbox"))
    db.add(AudioFile(id=3, root_id=3, path="/m/c.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="missing", has_cover=False,
                     location="inbox"))
    # Issue/DupGroup/DupMember non hanno una relationship() verso AudioFile:
    # senza un flush qui, l'ordine di flush degli INSERT non è garantito e con
    # foreign_keys=ON (engine unificato F2) può tentare l'INSERT di una riga
    # figlia prima di audio_file, violando la sua FK.
    db.flush()
    db.add(Issue(file_id=1, type="bad_bitrate", field=None, severity="error",
                 detail="x", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="missing_metadata", field="genre", severity="warning",
                 detail="x", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="resolved_one", field="x", severity="info",
                 detail="x", suggested_fix_json=None, status="dismissed"))
    db.add(DupGroup(id=1, match_kind="hash", keeper_file_id=1, signature="s1"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()


def test_library_stats(db, monkeypatch):
    from app.core.config import settings

    # "sources" ora conta le cartelle canoniche configurate (Settings), non più
    # le righe ScanRoot: azzeriamo entrambe per un conteggio deterministico
    # (library_root è già azzerato dalla guardia autouse _no_real_library_scan).
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    _seed_stats(db)
    with TestClient(app) as client:
        s = client.get("/api/organize/library/stats").json()
        assert s["files_total"] == 2          # solo i present
        assert s["by_ext"] == {"flac": 1, "mp3": 1}
        assert s["issues_by_severity"] == {"error": 1, "warning": 1}  # la dismissed esclusa
        assert s["dup_groups"] == 1
        assert s["sources"] == 0


def test_list_files_basic_and_indicators(db):
    _seed_stats(db)
    with TestClient(app) as client:
        rows = client.get("/api/organize/files").json()
        assert [r["path"] for r in rows] == ["/m/a.flac", "/m/b.mp3"]  # ordinati per path, no missing
        a = next(r for r in rows if r["id"] == 1)
        b = next(r for r in rows if r["id"] == 2)
        assert a["issue_count"] == 1 and a["worst_severity"] == "error"
        assert a["in_dup_group"] is True and b["in_dup_group"] is True
        assert b["worst_severity"] == "warning"  # la dismissed non conta


def test_list_files_filters(db):
    _seed_stats(db)
    with TestClient(app) as client:
        only_issues = client.get("/api/organize/files", params={"has_issues": True}).json()
        assert {r["id"] for r in only_issues} == {1, 2}
        by_inbox = client.get("/api/organize/files", params={"location": "inbox"}).json()
        assert [r["id"] for r in by_inbox] == [2]  # c.mp3 e' missing, escluso dal default status
        by_library = client.get("/api/organize/files", params={"location": "library"}).json()
        assert [r["id"] for r in by_library] == [1]
        searched = client.get("/api/organize/files", params={"q": "a.flac"}).json()
        assert [r["id"] for r in searched] == [1]
        missing = client.get("/api/organize/files", params={"status": "missing"}).json()
        assert [r["id"] for r in missing] == [3]


def test_list_files_sort_and_paging(db):
    _seed_stats(db)
    with TestClient(app) as client:
        ext_first = client.get("/api/organize/files", params={"sort": "title"}).json()
        assert len(ext_first) == 2
        page = client.get("/api/organize/files", params={"limit": 1, "offset": 1}).json()
        assert [r["id"] for r in page] == [2]


def test_list_files_cover_source(db):
    db.add(ScanRoot(id=3, path="/m", label="M"))
    db.add(AudioFile(id=1, root_id=3, path="/m/con-cover.flac", ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=True))
    db.add(AudioFile(id=2, root_id=3, path="/m/proposta.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=3, root_id=3, path="/m/niente.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.flush()  # Issue non ha una relationship() verso AudioFile: vedi _seed_stats
    # la proposta provider esiste solo come issue missing_cover aperta
    db.add(Issue(file_id=2, type="missing_cover", field="cover", severity="info",
                 detail="x", suggested_fix_json={"thumb_ref": "cover_cache/2.jpg"},
                 status="open"))
    # una accettata NON è più una proposta da mostrare come tale
    db.add(Issue(file_id=3, type="missing_cover", field="cover", severity="info",
                 detail="x", suggested_fix_json=None, status="accepted"))
    db.commit()

    with TestClient(app) as client:
        rows = {r["id"]: r["cover_source"] for r in client.get("/api/organize/files").json()}
    assert rows == {1: "embedded", 2: "provider", 3: None}
