from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue
from app.services import ai_tags


def _seed_missing(db, file_id, path, fields):
    db.add(AudioFile(id=file_id, root_id=1, path=path, ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist=None, title=None))
    for field in fields:
        db.add(Issue(file_id=file_id, type="missing_required_tag", field=field,
                     severity="error", detail=f"{field} mancante",
                     suggested_fix_json=None, status="open"))
    db.commit()


def test_ai_suggest_sets_fixes_without_accepting(db, monkeypatch):
    _seed_missing(db, 1, "/m/rataxes - acid face.mp3", ("artist", "title"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai_tags, "suggest",
                        lambda names: [{"artist": "rataxes", "title": "acid face"}])
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r == {"configured": True, "files": 1, "suggested": 2, "unresolved": 0}
        rows = client.get("/api/issues", params={"type": "missing_required_tag"}).json()
        by_field = {i["field"]: i for i in rows}
        assert by_field["artist"]["suggested_fix_json"] == {
            "field": "artist", "action": "retag", "to": "rataxes", "source": "ai"}
        assert by_field["artist"]["status"] == "open"  # NON accettata
        assert by_field["title"]["suggested_fix_json"]["to"] == "acid face"
        assert by_field["title"]["suggested_fix_json"]["source"] == "ai"


def test_ai_suggest_no_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r["configured"] is False
        assert r["suggested"] == 0


def test_ai_suggest_unresolved(db, monkeypatch):
    _seed_missing(db, 2, "/m/codice_strano.mp3", ("artist",))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai_tags, "suggest", lambda names: [{"artist": None, "title": None}])
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r["suggested"] == 0 and r["unresolved"] == 1


def test_ai_suggest_skips_already_suggested(db, monkeypatch):
    db.add(AudioFile(id=3, root_id=1, path="/m/x - y.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(Issue(file_id=3, type="missing_required_tag", field="artist", severity="error",
                 detail="artist mancante",
                 suggested_fix_json={"field": "artist", "action": "retag", "to": "Z"},
                 status="open"))
    db.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    called = {"n": 0}

    def _fake(names):
        called["n"] += 1
        return [{"artist": "x", "title": "y"} for _ in names]

    monkeypatch.setattr(ai_tags, "suggest", _fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r["files"] == 0 and r["suggested"] == 0  # niente da suggerire
        assert called["n"] == 0  # suggest non chiamato se non ci sono file
