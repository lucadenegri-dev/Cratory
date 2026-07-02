"""Catena del genere: normalizzazione e tracciamento della sorgente."""
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


def test_track_ha_genre_source(db):
    from app.models import Track
    t = Track(source_type="manual", title="T", artist="A",
              genre="Techno", genre_source="provider")
    db.add(t); db.commit(); db.refresh(t)
    assert t.genre_source == "provider"
