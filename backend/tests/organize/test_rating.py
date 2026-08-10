from mutagen.flac import FLAC
from mutagen.id3 import ID3, POPM, TPE1

from app.organize.integrations import tagio


def _set_id3_rating(path, rating, email="rekordbox"):
    try:
        t = ID3(path)
    except Exception:
        t = ID3()
    t.add(POPM(email=email, rating=rating, count=0))
    t.save(path)


def test_flac_read_clear_restore(copy_fixture, tmp_path):
    p = copy_fixture("flac", tmp_path / "a.flac")
    a = FLAC(p); a["artist"] = ["Keep Me"]; a["rating"] = ["204"]; a.save()
    assert tagio.read_rating(p) == "204"
    tagio.clear_rating(p)
    assert tagio.read_rating(p) is None
    assert tagio.read_tags(p).artist == "Keep Me"   # altri tag intatti
    tagio.set_rating(p, "204")
    assert tagio.read_rating(p) == "204"


def test_mp3_read_clear_restore(copy_fixture, tmp_path):
    p = copy_fixture("mp3", tmp_path / "a.mp3")
    _set_id3_rating(p, 196)
    ID3(p)  # sanity
    assert tagio.read_rating(p) == "196"
    tagio.clear_rating(p)
    assert tagio.read_rating(p) is None
    tagio.set_rating(p, "196")
    assert tagio.read_rating(p) == "196"


def test_aiff_read_clear(copy_fixture, tmp_path):
    from mutagen.aiff import AIFF
    p = copy_fixture("aiff", tmp_path / "a.aiff")
    a = AIFF(p)
    if a.tags is None:
        a.add_tags()
    a.tags.add(POPM(email="rekordbox", rating=128, count=0))
    a.save()
    assert tagio.read_rating(p) == "128"
    tagio.clear_rating(p)
    assert tagio.read_rating(p) is None


def test_no_rating_reads_none(copy_fixture, tmp_path):
    p = copy_fixture("flac", tmp_path / "a.flac")
    assert tagio.read_rating(p) is None
    tagio.clear_rating(p)  # no-op, non deve esplodere
    assert tagio.read_rating(p) is None
