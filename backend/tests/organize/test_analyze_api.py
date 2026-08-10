import time

from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, ScanRoot


def test_analyze_endpoint(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        # scan popola audio_file; poi analyze ricalcola
        client.post("/api/scan", json={"root_ids": [root_id]})
        deadline = time.time() + 5
        while time.time() < deadline:
            if client.get("/api/scan/status").json()["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        resp = client.post("/api/analyze")
        assert resp.status_code == 200
        body = resp.json()
        assert "issues_total" in body and "dup_groups" in body


def test_decisions_survive_reanalyze(db):
    """Test e2e: le decisioni utente (keeper override + issue dismissed) sopravvivono
    a un secondo POST /api/analyze che attraversa l'intera superficie API."""

    # --- Seed: radice + 2 file duplicati (fuzzy) + 1 file con issue dismissibile ---
    root = ScanRoot(path="/music/test", label="test")
    db.add(root)
    db.flush()

    # Due file con stesso artist+title+duration → gruppo fuzzy (content_hash diversi)
    f1 = AudioFile(
        root_id=root.id, path="/music/test/01-artist-title.flac",
        ext="flac", size_bytes=5000, content_hash="hash_flac_1",
        hash_method="file", status="present", has_cover=False,
        artist="DJ Test", title="Sample Track",
        album="Album A", album_artist="DJ Test",
        genre="House", year=2020, label="Label X",
        duration_s=200.0, bitrate=1411000, sample_rate=44100, channels=2,
    )
    f2 = AudioFile(
        root_id=root.id, path="/music/test/02-artist-title-copy.mp3",
        ext="mp3", size_bytes=3000, content_hash="hash_mp3_2",
        hash_method="file", status="present", has_cover=False,
        artist="DJ Test", title="Sample Track",
        album="Album A", album_artist="DJ Test",
        genre="House", year=2020, label="Label X",
        duration_s=200.0, bitrate=320000, sample_rate=44100, channels=2,
    )
    # Terzo file: ha genre=None → issue missing_metadata/genre (non auto-fixabile)
    f3 = AudioFile(
        root_id=root.id, path="/music/test/03-nogenre.mp3",
        ext="mp3", size_bytes=2000, content_hash="hash_mp3_3",
        hash_method="file", status="present", has_cover=False,
        artist="Other Artist", title="Another Track",
        genre=None, year=2021, label="Label Y",
        duration_s=180.0, bitrate=320000, sample_rate=44100, channels=2,
    )
    db.add_all([f1, f2, f3])
    db.commit()

    with TestClient(app) as client:
        # --- Step 1: prima analisi → crea gruppi e issue ---
        r = client.post("/api/analyze")
        assert r.status_code == 200
        body = r.json()
        assert body["dup_groups"] >= 1
        assert body["issues_total"] >= 1

        # --- Step 2: GET /api/duplicates → prendi il gruppo, scegli non-keeper ---
        groups = client.get("/api/duplicates").json()
        assert len(groups) == 1, f"atteso 1 gruppo dup, trovato {len(groups)}"
        grp = groups[0]
        grp_id = grp["id"]
        current_keeper = grp["keeper_file_id"]
        # Scegli un membro che NON è il keeper attuale
        non_keeper = next(m["file_id"] for m in grp["members"] if m["file_id"] != current_keeper)
        # Override keeper via API
        kr = client.post(f"/api/duplicates/{grp_id}/keeper", json={"file_id": non_keeper})
        assert kr.status_code == 200
        assert kr.json()["keeper_file_id"] == non_keeper
        assert kr.json()["keeper_overridden"] is True

        # --- Step 3: GET /api/issues → dismissi la missing_metadata/genre ---
        issues = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert len(issues) >= 1
        genre_issue = next((i for i in issues if i["field"] == "genre"), None)
        assert genre_issue is not None, "issue missing_metadata/genre non trovato"
        issue_id = genre_issue["id"]
        dr = client.post(f"/api/issues/{issue_id}/status", json={"status": "dismissed"})
        assert dr.status_code == 200

        # --- Step 4: seconda analisi (re-analyze) ---
        r2 = client.post("/api/analyze")
        assert r2.status_code == 200

        # --- Step 5: verifica che le decisioni siano sopravvissute ---
        # Keeper override preservato
        groups2 = client.get("/api/duplicates").json()
        assert len(groups2) == 1
        grp2 = groups2[0]
        assert grp2["keeper_file_id"] == non_keeper, (
            f"keeper_file_id dopo re-analyze: {grp2['keeper_file_id']}, atteso {non_keeper}"
        )
        assert grp2["keeper_overridden"] is True

        # Issue dismissed ancora dismissed
        issues2 = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        genre_issue2 = next((i for i in issues2 if i["id"] == issue_id), None)
        assert genre_issue2 is not None, "issue genre sparito dopo re-analyze"
        assert genre_issue2["status"] == "dismissed", (
            f"status issue dopo re-analyze: {genre_issue2['status']}, atteso 'dismissed'"
        )


def test_scan_job_runs_analysis(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        client.post("/api/scan", json={"root_ids": [root_id]})
        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1          # campo scan invariato (compat chunk 1)
        assert "analysis" in status["result"]             # analisi agganciata
        assert "issues_total" in status["result"]["analysis"]
