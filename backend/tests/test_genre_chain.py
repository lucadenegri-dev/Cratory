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


def _track(db, **kw):
    from app.models import Track
    t = Track(source_type="spotify", spotify_id="s1", platform_track_id="s1",
              title="T", artist="A", **kw)
    db.add(t); db.commit()
    return t


def test_provider_setta_genre_source(db):
    from app.services.feature_enrichment import apply_features
    t = _track(db)
    apply_features(t, {"genre_primary": "tech-house", "confidence": 80}, source="deezer")
    assert t.genre == "Tech House"
    assert t.genre_source == "provider"


def test_provider_non_sovrascrive_manuale(db):
    from app.services.feature_enrichment import apply_features
    t = _track(db, genre="Acid Techno", genre_source="manual")
    apply_features(t, {"genre_primary": "House", "confidence": 80}, source="deezer")
    assert t.genre == "Acid Techno" and t.genre_source == "manual"


def test_fill_identity_usa_tag_file_come_ultima_spiaggia(db, tmp_path):
    from app.services.library_index import _fill_identity
    t = _track(db)
    _fill_identity(t, {"artist": "A", "title": "T", "genre": "  deep   house "},
                   tmp_path / "A - T.mp3")
    assert t.genre == "Deep House"
    assert t.genre_source == "file_tag"


def test_fill_identity_non_tocca_genere_esistente(db, tmp_path):
    from app.services.library_index import _fill_identity
    t = _track(db, genre="Techno", genre_source="provider")
    _fill_identity(t, {"artist": "A", "title": "T", "genre": "House"},
                   tmp_path / "A - T.mp3")
    assert t.genre == "Techno" and t.genre_source == "provider"


def test_ai_entra_solo_se_genere_vuoto(db, monkeypatch):
    from app.services import genre_ai
    from app.services.feature_enrichment import _ai_genre_pass
    t = _track(db)
    t2 = _track(db, genre="House", genre_source="provider")
    monkeypatch.setattr(genre_ai, "suggest_genres",
                        lambda tracks: {tr.id: "Minimal Techno" for tr in tracks})
    applied = _ai_genre_pass(db, [t, t2], force=False)
    assert applied == 1
    assert t.genre == "Minimal Techno" and t.genre_source == "ai"
    assert t2.genre == "House" and t2.genre_source == "provider"


def test_ai_non_configurata_o_errore_neutra(db, monkeypatch):
    from app.services import genre_ai
    from app.services.feature_enrichment import _ai_genre_pass
    t = _track(db)
    monkeypatch.setattr(genre_ai, "suggest_genres", lambda tracks: {})
    assert _ai_genre_pass(db, [t], force=False) == 0
    assert t.genre is None and t.genre_source is None
