# backend/tests/test_provider_rescan_core.py
from app.models import AudioFile, Issue, ScanRoot
from app.services import provider_rescan


class FakeMB:
    def __init__(self, by_title):
        self.by_title = by_title

    def lookup(self, *, title, artist, isrc=None, mbid=None):
        return self.by_title.get(title)


class FakeDiscogs:
    def lookup(self, *, artist, title):
        return None


def _add(db, **over):
    root = db.query(ScanRoot).first()
    if root is None:
        root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, ext="mp3", size_bytes=1, hash_method="file",
                  status="present", **over)
    db.add(f); db.flush()
    return f


def test_proposes_override_when_genre_differs(db):
    _add(db, path="/m/House/a.mp3", title="A", artist="X", genre="house")
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    res = provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.field == "genre" and iss.status == "open"
    assert iss.suggested_fix_json == {"field": "genre", "action": "retag",
                                      "to": "House", "source": "provider",
                                      "confidence": "high"}
    assert res["proposed_high"] == 1 and res["proposed_text"] == 0


def test_no_override_when_genre_equal(db):
    _add(db, path="/m/a.mp3", title="A", artist="X", genre="House")
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    assert db.query(Issue).filter_by(type="provider_override").count() == 0


def test_folder_filter_scopes_files(db):
    _add(db, path="/m/House/a.mp3", title="A", artist="X", genre="x")
    _add(db, path="/m/Techno/b.mp3", title="B", artist="Y", genre="x")
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 80},
                 "B": {"genre_primary": "Techno", "confidence": 80}})
    res = provider_rescan.rescan(db, folder="House", fields=["genre"],
                                 mb=mb, discogs=FakeDiscogs())
    assert res["scanned"] == 1
    assert db.query(Issue).filter_by(type="provider_override").count() == 1


def test_skips_field_with_open_inspector_issue(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    db.add(Issue(file_id=f.id, type="dirty_genre", field="genre",
                 severity="warning", detail="sporco", status="open"))
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    assert db.query(Issue).filter_by(type="provider_override").count() == 0


def test_deletes_stale_open_override_when_now_equal(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="House")
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="old",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    assert db.query(Issue).filter_by(type="provider_override").count() == 0


def test_keeps_accepted_override_untouched(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="old",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Deep House", "source": "provider",
                                     "confidence": "text"}, status="accepted"))
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "accepted" and iss.suggested_fix_json["to"] == "Deep House"
