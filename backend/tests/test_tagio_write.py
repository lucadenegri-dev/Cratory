from app.integrations import tagio
from app.integrations.content_hash import compute


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


def test_clear_field_wav(copy_fixture, tmp_path):
    f = copy_fixture("wav", tmp_path / "a.wav")
    tagio.write_tags(f, {"artist": "X"})
    tagio.write_tags(f, {"artist": None})
    assert tagio.read_tags(f).artist is None
