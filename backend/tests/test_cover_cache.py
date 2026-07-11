from app.services import cover_cache


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
