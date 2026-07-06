from app.services.genre_norm import normalize_genre


def test_normalize_genre_alias_and_casing():
    assert normalize_genre("dnb") == "Drum & Bass"
    assert normalize_genre("tech-house") == "Tech House"
    assert normalize_genre("  IDM ") == "IDM"
    assert normalize_genre("") is None
    assert normalize_genre(None) is None
