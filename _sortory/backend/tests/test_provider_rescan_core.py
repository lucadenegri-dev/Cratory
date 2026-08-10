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
                                      "confidence": "strong"}
    assert res["proposed_strong"] == 1 and res["proposed_weak"] == 0


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


def _override(db, file_id, to, status):
    db.add(Issue(file_id=file_id, type="provider_override", field="genre",
                 severity="info", detail="x",
                 suggested_fix_json={"field": "genre", "action": "retag", "to": to,
                                     "source": "provider", "confidence": "text"},
                 status=status))
    db.commit()


def test_accepted_kept_without_flag_even_if_differs(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    _override(db, f.id, "Old", "accepted")
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "accepted" and iss.suggested_fix_json["to"] == "Old"


def test_include_accepted_reopens_when_differs(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    _override(db, f.id, "Old", "accepted")
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    res = provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs(),
                                 include_accepted=True)
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "open" and iss.suggested_fix_json["to"] == "House"
    assert iss.suggested_fix_json["confidence"] == "strong"
    assert res["proposed_strong"] == 1


def test_include_dismissed_reopens_when_differs(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    _override(db, f.id, "Old", "dismissed")
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs(),
                           include_dismissed=True)
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "open" and iss.suggested_fix_json["to"] == "House"


def test_include_accepted_not_reopened_when_equal(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="House")
    _override(db, f.id, "House", "accepted")
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs(),
                           include_accepted=True)
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "accepted"  # provider == file → non riaperto


def test_include_dismissed_does_not_touch_accepted(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    _override(db, f.id, "Old", "accepted")
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs(),
                           include_dismissed=True)  # solo dismissed, non accepted
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "accepted"


# --- estensioni: artist/title, covers, only_new -----------------------------

class FakeCAA:
    def front_thumb(self, mbid):
        return b"IMG" if mbid else None

    def front_url(self, mbid):
        return f"caa/{mbid}"


def test_proposes_artist_title_override(db):
    _add(db, path="/m/a.mp3", title="old t", artist="old a", genre="House")
    db.commit()
    mb = FakeMB({"old t": {"canonical_artist": "New A", "canonical_title": "New T",
                           "confidence": 95}})
    res = provider_rescan.rescan(db, fields=["artist", "title"], mb=mb, discogs=FakeDiscogs())
    overrides = {i.field: i for i in db.query(Issue).filter_by(type="provider_override")}
    assert set(overrides) == {"artist", "title"}
    assert overrides["artist"].suggested_fix_json["to"] == "New A"
    assert overrides["title"].suggested_fix_json["to"] == "New T"
    assert res["proposed_strong"] == 2


def test_covers_fetched_for_files_without_cover(db):
    _add(db, path="/m/a.mp3", title="A", artist="X", genre="House", has_cover=False)
    db.commit()
    mb = FakeMB({"A": {"canonical_title": "A", "confidence": 95, "release_mbids": ["r1"]}})
    res = provider_rescan.rescan(db, fields=[], covers=True, mb=mb,
                                 discogs=FakeDiscogs(), caa=FakeCAA())
    cover_iss = db.query(Issue).filter_by(type="missing_cover").one()
    assert cover_iss.field == "cover" and cover_iss.status == "open"
    assert res["covers"] == 1


def test_covers_skipped_when_file_has_cover(db):
    _add(db, path="/m/a.mp3", title="A", artist="X", genre="House", has_cover=True)
    db.commit()
    mb = FakeMB({"A": {"canonical_title": "A", "confidence": 95, "release_mbids": ["r1"]}})
    res = provider_rescan.rescan(db, fields=[], covers=True, mb=mb,
                                 discogs=FakeDiscogs(), caa=FakeCAA())
    assert db.query(Issue).filter_by(type="missing_cover").count() == 0
    assert res["covers"] == 0


def test_only_new_scopes_to_fresh_files(db):
    from datetime import datetime, timedelta
    t0 = datetime(2020, 1, 1)
    new = _add(db, path="/m/new.mp3", title="A", artist="X", genre="x")
    old = _add(db, path="/m/old.mp3", title="B", artist="Y", genre="x")
    new.first_seen_at = t0
    new.last_scanned_at = t0
    old.first_seen_at = t0
    old.last_scanned_at = t0 + timedelta(days=1)
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95},
                 "B": {"genre_primary": "Techno", "confidence": 95}})
    res = provider_rescan.rescan(db, fields=["genre"], only_new=True,
                                 mb=mb, discogs=FakeDiscogs())
    assert res["scanned"] == 1
    ov = db.query(Issue).filter_by(type="provider_override").one()
    assert db.get(AudioFile, ov.file_id).path == "/m/new.mp3"
