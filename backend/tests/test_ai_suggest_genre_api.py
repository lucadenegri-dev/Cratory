from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue
from app.services import ai_tags


def _seed_genre(db, file_id, path, *, artist=None, title=None,
                artist_fix=None, title_fix=None):
    db.add(AudioFile(id=file_id, root_id=1, path=path, ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist=artist, title=title))
    db.add(Issue(file_id=file_id, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    for field, fixval in (("artist", artist_fix), ("title", title_fix)):
        if fixval is not None:
            db.add(Issue(file_id=file_id, type="missing_required_tag", field=field,
                         severity="error", detail=f"{field} mancante",
                         suggested_fix_json={"field": field, "action": "retag",
                                             "to": fixval}, status="open"))
    db.commit()


def test_genre_uses_effective_artist_title(db, monkeypatch):
    # tag vuoti, ma artista/titolo presenti nei suggested_fix (feature precedente)
    _seed_genre(db, 1, "/m/x.mp3", artist_fix="ANNA", title_fix="Hidden Beauties")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake(descriptions):
        captured["descs"] = descriptions
        return ["Tech House"]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r == {"configured": True, "files": 1, "suggested": 1, "unresolved": 0}
        assert captured["descs"] == ["ANNA - Hidden Beauties"]
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        genre = next(i for i in rows if i["field"] == "genre")
        assert genre["suggested_fix_json"] == {"field": "genre", "action": "retag",
                                               "to": "Tech House"}
        assert genre["status"] == "open"


def test_genre_falls_back_to_filename(db, monkeypatch):
    _seed_genre(db, 2, "/m/Some Artist - Some Track.mp3")  # nessun artista/titolo noto
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake(descriptions):
        captured["descs"] = descriptions
        return ["Acid"]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        client.post("/api/issues/ai-suggest-genre")
        assert captured["descs"] == ["Some Artist - Some Track"]


def test_genre_no_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r["configured"] is False and r["suggested"] == 0


def test_genre_unresolved(db, monkeypatch):
    _seed_genre(db, 3, "/m/y.mp3", artist="Live", title="Set")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai_tags, "suggest_genres", lambda d: [None])
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r["suggested"] == 0 and r["unresolved"] == 1


def test_genre_skips_already_suggested(db, monkeypatch):
    db.add(AudioFile(id=4, root_id=1, path="/m/z.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(Issue(file_id=4, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante",
                 suggested_fix_json={"field": "genre", "action": "retag", "to": "House"},
                 status="open"))
    db.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    called = {"n": 0}

    def fake(d):
        called["n"] += 1
        return ["X" for _ in d]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r["files"] == 0 and r["suggested"] == 0
        assert called["n"] == 0
