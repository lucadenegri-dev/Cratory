import shutil

from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3

from app.integrations import content_hash


def test_two_identical_copies_same_hash(copy_fixture, tmp_path):
    a = copy_fixture("flac", tmp_path / "a.flac")
    b = copy_fixture("flac", tmp_path / "b.flac")
    ha, ma = content_hash.compute(a, ".flac")
    hb, mb = content_hash.compute(b, ".flac")
    assert ha == hb and ma == mb == "stream" and ha is not None


def test_mp3_hash_stable_after_retag(copy_fixture, tmp_path):
    f = copy_fixture("mp3", tmp_path / "a.mp3")
    h1, m1 = content_hash.compute(f, ".mp3")
    audio = EasyMP3(f)
    if audio.tags is None:
        audio.add_tags()
    audio["artist"] = "Pinco Pallino"
    audio["title"] = "Una traccia con un titolo lungo"
    audio.save()
    h2, m2 = content_hash.compute(f, ".mp3")
    assert m1 == "stream" and h1 == h2


def test_flac_hash_stable_after_retag(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    h1, m1 = content_hash.compute(f, ".flac")
    audio = FLAC(f)
    audio["artist"] = "Pinco Pallino"
    audio["title"] = "Titolo"
    audio.save()
    h2, m2 = content_hash.compute(f, ".flac")
    assert m1 == "stream" and h1 == h2


def test_m4a_uses_file_method(copy_fixture, tmp_path):
    f = copy_fixture("m4a", tmp_path / "a.m4a")
    h, m = content_hash.compute(f, ".m4a")
    assert m == "file" and h is not None


def test_unreadable_returns_none(tmp_path):
    h, m = content_hash.compute(str(tmp_path / "nope.mp3"), ".mp3")
    assert h is None
