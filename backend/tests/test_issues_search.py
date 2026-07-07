from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m")
    db.add(root)
    db.flush()
    a = AudioFile(root_id=root.id, path="/m/anna-track.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="ANNA", title="Hidden")
    b = AudioFile(root_id=root.id, path="/m/kai.wav", ext="wav", size_bytes=1,
                  hash_method="file", status="present", artist="Kai Tracid", title="Tracid Theme")
    db.add_all([a, b])
    db.flush()
    db.add(Issue(file_id=a.id, type="missing_metadata", field="genre",
                 severity="warning", detail="x", status="open"))
    db.add(Issue(file_id=b.id, type="missing_metadata", field="genre",
                 severity="warning", detail="x", status="open"))
    db.commit()


def test_search_by_artist(db):
    _seed(db)
    rows = client.get("/api/issues", params={"q": "kai"}).json()
    assert {r["artist"] for r in rows} == {"Kai Tracid"}


def test_search_by_title(db):
    _seed(db)
    rows = client.get("/api/issues", params={"q": "hidden"}).json()
    assert len(rows) == 1 and rows[0]["title"] == "Hidden"


def test_search_by_path(db):
    _seed(db)
    rows = client.get("/api/issues", params={"q": "anna-track"}).json()
    assert len(rows) == 1 and rows[0]["file_path"].endswith("anna-track.mp3")


def test_no_query_returns_all(db):
    _seed(db)
    rows = client.get("/api/issues").json()
    assert len(rows) == 2
