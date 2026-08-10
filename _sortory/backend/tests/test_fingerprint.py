from app.models import AudioFile, ScanRoot
from app.services.fingerprint import fingerprint_files


class _FakeAcoustID:
    def __init__(self, mapping): self.mapping = mapping
    def identify(self, path): return self.mapping.get(path, [])


def test_fingerprint_sets_mbid_above_threshold(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present")
    db.add(f); db.commit()
    client = _FakeAcoustID({"/m/a.mp3": [{"mbid": "MB1", "score": 0.9}]})
    report = fingerprint_files(db, client, threshold=0.5)
    db.refresh(f)
    assert f.mbid == "MB1"
    assert report["identified"] == 1


def test_low_score_leaves_mbid_none(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/b.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present")
    db.add(f); db.commit()
    client = _FakeAcoustID({"/m/b.mp3": [{"mbid": "MB2", "score": 0.2}]})
    report = fingerprint_files(db, client, threshold=0.5)
    db.refresh(f)
    assert f.mbid is None
    assert report["below_threshold"] == 1
