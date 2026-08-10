from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, DupGroup, DupMember


def _seed(db):
    for i, ext in ((1, "flac"), (2, "mp3")):
        db.add(AudioFile(id=i, root_id=1, path=f"/m/{i}.{ext}", ext=ext, size_bytes=1,
                         hash_method="file", status="present", has_cover=False,
                         artist="A", title="T", duration_s=200.0, bitrate=320000,
                         content_hash=f"h{i}"))
    grp = DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, keeper_overridden=False,
                   dismissed=False, signature="sig")
    db.add(grp)
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()


def test_list_duplicates(db):
    _seed(db)
    with TestClient(app) as client:
        groups = client.get("/api/duplicates").json()
        assert len(groups) == 1
        assert {m["file_id"] for m in groups[0]["members"]} == {1, 2}
        assert groups[0]["keeper_file_id"] == 1


def test_set_keeper(db):
    _seed(db)
    with TestClient(app) as client:
        resp = client.post("/api/duplicates/1/keeper", json={"file_id": 2})
        assert resp.status_code == 200
        g = client.get("/api/duplicates").json()[0]
        assert g["keeper_file_id"] == 2 and g["keeper_overridden"] is True
        actions = {m["file_id"]: m["action"] for m in g["members"]}
        assert actions == {2: "keep", 1: "remove"}


def test_set_keeper_non_member_rejected(db):
    _seed(db)
    with TestClient(app) as client:
        assert client.post("/api/duplicates/1/keeper", json={"file_id": 99}).status_code == 400


def test_dismiss(db):
    _seed(db)
    with TestClient(app) as client:
        assert client.post("/api/duplicates/1/dismiss").status_code == 200
        g = client.get("/api/duplicates").json()[0]
        assert g["dismissed"] is True
        assert all(m["action"] == "keep" for m in g["members"])
