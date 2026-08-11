import os

from fastapi.testclient import TestClient

from app.organize.integrations import tagio
from app.main import app
from app.organize.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db, path, **kw):
    if db.get(ScanRoot, 1) is None:
        db.add(ScanRoot(id=1, path=os.path.dirname(path)))
    d = dict(id=1, root_id=1, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="Old", title="T")
    d.update(kw)
    db.add(AudioFile(**d))
    db.commit()


def test_post_tags_returns_updated_row(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    _seed(db, f, artist="Old")
    r = client.post("/api/organize/files/1/tags", json={"artist": "New", "year": "2003"})
    assert r.status_code == 200
    body = r.json()
    assert body["artist"] == "New" and body["year"] == 2003
    assert body["album_artist"] is None and body["track_no"] is None
    assert tagio.read_tags(f).artist == "New"


def test_post_tags_closes_issue_and_updates_count(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    _seed(db, f, artist=None)
    db.add(Issue(file_id=1, type="missing_required_tag", field="artist",
                 severity="error", detail="no artist", status="open"))
    db.commit()
    r = client.post("/api/organize/files/1/tags", json={"artist": "Fixed"})
    assert r.status_code == 200
    assert r.json()["issue_count"] == 0


def test_post_tags_404_when_missing(db):
    r = client.post("/api/organize/files/999/tags", json={"artist": "X"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "file_not_found"


def test_post_tags_409_when_file_gone(db, tmp_path):
    _seed(db, str(tmp_path / "gone.flac"))
    r = client.post("/api/organize/files/1/tags", json={"artist": "X"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "file_not_writable"


def test_post_tags_400_on_bad_year(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    _seed(db, f)
    r = client.post("/api/organize/files/1/tags", json={"year": "abc"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "value_invalid"


def test_post_tags_value_invalid_carries_params(db, tmp_path, copy_fixture):
    # il codice errore porta il campo (+ motivo) come params, così il frontend può
    # tradurre "'year' dev'essere un numero" invece di ricadere sul testo inglese.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    _seed(db, f)
    d = client.post("/api/organize/files/1/tags", json={"year": "abc"}).json()["detail"]
    assert d["code"] == "value_invalid"
    assert d["params"]["field"] == "year"
    assert d["params"]["reason"] == "number"
