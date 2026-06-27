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


def test_corrupt_flac_no_collision_falls_back_to_file(tmp_path):
    """FLAC troncato/corrotto: nessuna collisione, fallback a method='file'.

    Due file che iniziano con b'fLaC' ma hanno byte spazzatura diversi dopo il
    marker non devono produrre lo stesso hash (no blake2b di slice vuota).
    Entrambi devono usare method='file' (parser non è riuscito a trovare
    l'audio frame range) e i due hash devono essere distinti.
    """
    # File A: marker fLaC + troncato con 0xFF (nessun valid metadata block)
    corrupt_a = tmp_path / "corrupt_a.flac"
    corrupt_a.write_bytes(b"fLaC" + b"\xff" * 8)

    # File B: marker fLaC + troncato con 0x00 (dati diversi → hash diverso)
    corrupt_b = tmp_path / "corrupt_b.flac"
    corrupt_b.write_bytes(b"fLaC" + b"\x00" * 8)

    ha, ma = content_hash.compute(str(corrupt_a), ".flac")
    hb, mb = content_hash.compute(str(corrupt_b), ".flac")

    # Entrambi non-None
    assert ha is not None, "hash di corrupt_a non deve essere None"
    assert hb is not None, "hash di corrupt_b non deve essere None"

    # Fallback a file (parser non è riuscito)
    assert ma == "file", f"corrupt_a: atteso method='file', ottenuto '{ma}'"
    assert mb == "file", f"corrupt_b: atteso method='file', ottenuto '{mb}'"

    # Nessuna collisione tra file con contenuto diverso
    assert ha != hb, "file corrotti con byte diversi non devono avere lo stesso hash"
