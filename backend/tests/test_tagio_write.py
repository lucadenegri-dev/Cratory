import struct

from app.integrations import tagio
from app.integrations.content_hash import compute


def _append_malformed_riff_tail(path):
    """Riproduce il difetto reale: una coda di byte non-chunk dopo i chunk validi,
    coperta dalla dimensione dichiarata del RIFF. mutagen ci si blocca sopra e non
    rilegge più l'`id3 ` appeso → i tag scritti risultano invisibili."""
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    data += b"\x04\x00\x05\x00" + struct.pack("<I", 262149) + b"\x00" * 200
    struct.pack_into("<I", data, 4, len(data) - 8)  # RIFF size copre anche la coda
    with open(path, "wb") as fh:
        fh.write(data)


def test_write_then_read(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "Pinco", "title": "Titolo"})
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco" and tags.title == "Titolo"


def test_content_hash_stable_after_write(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    before = compute(f, ".flac")[0]
    tagio.write_tags(f, {"artist": "Nuovo Artista"})
    assert compute(f, ".flac")[0] == before  # hash dello stream invariato


def test_clear_field(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "X"})
    tagio.write_tags(f, {"artist": None})
    assert tagio.read_tags(f).artist is None


# --- formati ID3-based senza modalità easy (WAV/AIFF) -----------------------
# Regressione: write_tags assumeva l'assegnazione di stringhe (easy), che su
# WAV/AIFF colpisce un ID3 grezzo → "X not a Frame instance".

def test_write_then_read_wav(copy_fixture, tmp_path):
    f = copy_fixture("wav", tmp_path / "a.wav")
    tagio.write_tags(f, {"artist": "Kai Tracid", "title": "Tracid Theme",
                         "genre": "Acid Techno"})
    tags = tagio.read_tags(f)
    assert tags.artist == "Kai Tracid"
    assert tags.title == "Tracid Theme"
    assert tags.genre == "Acid Techno"


def test_write_then_read_aiff(copy_fixture, tmp_path):
    f = copy_fixture("aiff", tmp_path / "a.aiff")
    tagio.write_tags(f, {"artist": "Plastikman", "title": "Spastik"})
    tags = tagio.read_tags(f)
    assert tags.artist == "Plastikman" and tags.title == "Spastik"


def test_write_then_read_wav_with_malformed_riff_tail(copy_fixture, tmp_path):
    # WAV con coda RIFF corrotta (tipico di alcuni file da DJ pool): mutagen scrive
    # ma non rilegge i tag. write_tags deve riparare il contenitore e persistere.
    f = copy_fixture("wav", tmp_path / "bad.wav")
    _append_malformed_riff_tail(f)
    dur_before = tagio.read_info(f).duration_s
    tagio.write_tags(f, {"artist": "Hermeth", "title": "Strictly Acid",
                         "genre": "Acid Techno"})
    tags = tagio.read_tags(f)
    assert tags.artist == "Hermeth"
    assert tags.title == "Strictly Acid"
    assert tags.genre == "Acid Techno"
    # l'audio non deve essere toccato dalla riparazione
    assert tagio.read_info(f).duration_s == dur_before


def test_clear_field_wav(copy_fixture, tmp_path):
    f = copy_fixture("wav", tmp_path / "a.wav")
    tagio.write_tags(f, {"artist": "X"})
    tagio.write_tags(f, {"artist": None})
    assert tagio.read_tags(f).artist is None
