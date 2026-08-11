from app.organize.services import cover_cache


def test_save_read_roundtrip(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    ref = cover_cache.save_thumb(42, b"\xff\xd8jpg")
    assert ref == "cover_cache/42.jpg"
    assert cover_cache.read_thumb(42) == b"\xff\xd8jpg"


def test_read_missing_is_none(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    assert cover_cache.read_thumb(999) is None


def test_read_race_between_exists_and_open_returns_none(tmp_path, monkeypatch):
    """Tra l'exists() e l'open() qualcuno può far sparire il file (es. una
    drop_thumb concorrente durante la delete di una sorgente): non deve
    diventare un 500, la richiesta della thumb gira su ogni riga di tabella."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    cover_cache.save_thumb(7, b"\xff\xd8jpg")

    real_open = open
    path = cover_cache.thumb_path(7)

    def flaky_open(file, *a, **kw):
        if file == path:
            raise OSError("simulated race: removed between exists() and open()")
        return real_open(file, *a, **kw)

    monkeypatch.setattr("builtins.open", flaky_open)
    assert cover_cache.read_thumb(7) is None
