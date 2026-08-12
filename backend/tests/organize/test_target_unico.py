"""La destinazione di un Apply è una sola: la libreria."""

from app.organize.services import planning


def test_target_root_e_library_root(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "library_root", "/Users/x/Music/Library")
    assert planning.target_root() == "/Users/x/Music/Library"


def test_root_targets_non_esiste_piu():
    assert not hasattr(planning, "root_targets")
    assert not hasattr(planning, "set_root_target")
