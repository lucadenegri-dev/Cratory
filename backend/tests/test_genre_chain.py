"""Catena del genere: normalizzazione e fallback dal tag del file."""
import pytest

from app.services.genre_norm import normalize_genre


@pytest.mark.parametrize("raw,expected", [
    ("  tech house ", "Tech House"),
    ("tech-house", "Tech House"),
    ("TECH  HOUSE", "Tech House"),
    ("drum'n'bass", "Drum & Bass"),
    ("dnb", "Drum & Bass"),
    ("Deep House", "Deep House"),
    ("EDM", "EDM"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_normalize_genre(raw, expected):
    assert normalize_genre(raw) == expected


def _track(db, **kw):
    from app.models import Track
    t = Track(source_type="spotify", spotify_id="s1", platform_track_id="s1",
              title="T", artist="A", **kw)
    db.add(t); db.commit()
    return t


def test_fill_identity_usa_tag_file_come_ultima_spiaggia(db, tmp_path):
    from app.services.library_index import _fill_identity
    t = _track(db)
    _fill_identity(t, {"artist": "A", "title": "T", "genre": "  deep   house "},
                   tmp_path / "A - T.mp3")
    assert t.genre == "Deep House"


def test_fill_identity_non_tocca_genere_esistente(db, tmp_path):
    from app.services.library_index import _fill_identity
    t = _track(db, genre="Techno")
    _fill_identity(t, {"artist": "A", "title": "T", "genre": "House"},
                   tmp_path / "A - T.mp3")
    assert t.genre == "Techno"
