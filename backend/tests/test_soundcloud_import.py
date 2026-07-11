"""Integrazione SoundCloud via yt-dlp (solo metadati) e normalizzazione."""

import pytest

from app.integrations import soundcloud as sc
from app.integrations.soundcloud import (
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_likes,
    fetch_playlist,
    is_likes_url,
)


# --- helper fixture: entry flat e info dict realistici -----------------------

def _entry(i: int = 1, title: str = "Artist X - Cool Track", uploader: str | None = "channelY", **kw) -> dict:
    e = {
        "_type": "url",
        "id": str(1000 + i),
        "url": f"https://soundcloud.com/u/track-{i}",
        "title": title,
        "duration": 245.0,
        "uploader": uploader,
    }
    e.update(kw)
    return e


def _info(entries: list, **kw) -> dict:
    info = {
        "id": "12345",
        "title": "Deep Crate",
        "uploader": "digger",
        "webpage_url": "https://soundcloud.com/digger/sets/deep-crate",
        "entries": entries,
    }
    info.update(kw)
    return info


# --- validazione URL (pura, niente rete) --------------------------------------

def test_fetch_playlist_rifiuta_url_non_http():
    with pytest.raises(SoundCloudInvalidUrl):
        fetch_playlist("file:///etc/passwd")


def test_fetch_playlist_rifiuta_host_non_soundcloud():
    with pytest.raises(SoundCloudInvalidUrl):
        fetch_playlist("https://example.com/sets/x")


def test_is_likes_url():
    assert is_likes_url("https://soundcloud.com/luca/likes")
    assert is_likes_url("https://soundcloud.com/luca/likes/")
    assert not is_likes_url("https://soundcloud.com/luca/sets/crate")


# --- fetch con estrattore mockato ----------------------------------------------

def test_fetch_playlist_materializza_le_entries(monkeypatch):
    def fake_extract(url, *, limit=None):
        return _info(iter([_entry(1), _entry(2)]))  # generatore: va materializzato

    monkeypatch.setattr(sc, "_extract", fake_extract)
    info = fetch_playlist("https://soundcloud.com/digger/sets/deep-crate")
    assert isinstance(info["entries"], list)
    assert len(info["entries"]) == 2


def test_fetch_likes_costruisce_url_e_passa_il_limit(monkeypatch):
    seen = {}

    def fake_extract(url, *, limit=None):
        seen["url"] = url
        seen["limit"] = limit
        return _info([_entry(1)])

    monkeypatch.setattr(sc, "_extract", fake_extract)
    fetch_likes("  @luca ", limit=50)
    assert seen["url"] == "https://soundcloud.com/luca/likes"
    assert seen["limit"] == 50


def test_fetch_likes_senza_username_solleva():
    with pytest.raises(SoundCloudError):
        fetch_likes("   ")
