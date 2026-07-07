from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m")
    db.add(root)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="ANNA", title="A",
                  album="Alpha", genre="House", year=2023, label="Diynamic"),
        AudioFile(root_id=root.id, path="/m/b.wav", ext="wav", size_bytes=1,
                  hash_method="file", status="present", artist="Kai Tracid", title="B",
                  album="Beta", genre="Trance", year=2002, label="Tracid Traxxx"),
        AudioFile(root_id=root.id, path="/m/c.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="ANNA", title="C",
                  album="Gamma", genre="House", year=2021, label="Diynamic"),
    ])
    db.commit()


def test_files_filter_by_genre(db):
    _seed(db)
    rows = client.get("/api/files", params={"genre": "House"}).json()
    assert {r["title"] for r in rows} == {"A", "C"}
    assert all(r["genre"] == "House" for r in rows)


def test_files_filter_by_ext_and_year(db):
    _seed(db)
    rows = client.get("/api/files", params={"ext": "mp3", "year": 2021}).json()
    assert {r["title"] for r in rows} == {"C"}


def test_files_filter_by_label(db):
    _seed(db)
    rows = client.get("/api/files", params={"label": "Tracid Traxxx"}).json()
    assert {r["title"] for r in rows} == {"B"}


def test_filerow_exposes_tag_fields(db):
    _seed(db)
    row = next(r for r in client.get("/api/files").json() if r["title"] == "A")
    assert row["album"] == "Alpha" and row["genre"] == "House"
    assert row["year"] == 2023 and row["label"] == "Diynamic"


def test_library_facets_distinct_sorted(db):
    _seed(db)
    f = client.get("/api/library/facets").json()
    assert f["genre"] == ["House", "Trance"]
    assert f["ext"] == ["mp3", "wav"]
    assert f["year"] == [2002, 2021, 2023]
    assert f["label"] == ["Diynamic", "Tracid Traxxx"]
    assert "ANNA" in f["artist"] and "Kai Tracid" in f["artist"]
