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


# --- normalizzazione -----------------------------------------------------------

from app.services.playlist_import import normalize_soundcloud_item, split_artist_title


def test_split_alla_prima_occorrenza():
    # trattini multipli: solo il primo separa artista e titolo
    assert split_artist_title("Artist X - Cool Track - Extended", "chan") == (
        "Artist X", "Cool Track - Extended",
    )


def test_split_senza_separatore_usa_uploader():
    assert split_artist_title("Cool Track (Bootleg)", "channelY") == ("channelY", "Cool Track (Bootleg)")


def test_split_senza_separatore_ne_uploader():
    assert split_artist_title("Cool Track", None) == (None, "Cool Track")


def test_split_titolo_vuoto():
    assert split_artist_title(None, "channelY") == ("channelY", None)


def test_normalize_entry_completa():
    norm = normalize_soundcloud_item(_entry(1))
    assert norm is not None
    assert norm.platform == "soundcloud"
    assert norm.platform_track_id == "1001"
    assert norm.artist == "Artist X"
    assert norm.title == "Cool Track"
    assert norm.duration_seconds == 245
    assert norm.url == "https://soundcloud.com/u/track-1"
    assert norm.isrc is None


def test_normalize_entry_senza_id_scartata():
    assert normalize_soundcloud_item(_entry(1, id=None)) is None
    assert normalize_soundcloud_item({}) is None
    assert normalize_soundcloud_item(None) is None


def test_normalize_campi_mancanti():
    norm = normalize_soundcloud_item({"id": 42, "title": "Solo Titolo"})
    assert norm is not None
    assert norm.platform_track_id == "42"  # id numerico -> stringa
    assert norm.artist is None
    assert norm.title == "Solo Titolo"
    assert norm.duration_seconds is None
    assert norm.artwork_url is None


# --- like: preview selettiva e import dei selezionati ---------------------------

from app.models import Playlist
from app.services.playlist_import import (
    SC_LIKED_PLAYLIST_NAME,
    import_selected_soundcloud_likes,
    preview_soundcloud_likes,
)


def test_preview_marca_gia_importate(db):
    entries = [_entry(1), _entry(2, title="Other - Tune")]
    # primo import: entra solo la traccia 1
    import_selected_soundcloud_likes(db, entries, ["1001"])
    preview = preview_soundcloud_likes(db, entries)
    assert [p["track_id"] for p in preview] == ["1001", "1002"]
    assert preview[0]["already_imported"] is True
    assert preview[1]["already_imported"] is False
    assert preview[0]["artist"] == "Artist X"


def test_import_selected_filtra_e_riusa_la_playlist_liked(db):
    entries = [_entry(1), _entry(2, title="Other - Tune"), _entry(3, title="Third - One")]
    r1 = import_selected_soundcloud_likes(db, entries, ["1001", "1003"])
    assert r1["created"] == 2
    # secondo giro: idempotente sulla stessa playlist di sistema, additivo
    r2 = import_selected_soundcloud_likes(db, entries, ["1002"])
    assert r2["created"] == 1
    assert r2["removed"] == 0
    liked = db.query(Playlist).filter(
        Playlist.platform == "soundcloud", Playlist.kind == "liked",
    ).all()
    assert len(liked) == 1
    assert liked[0].name == SC_LIKED_PLAYLIST_NAME
    assert liked[0].track_count == 3


def test_import_popola_soundcloud_id_come_spotify(db):
    """Parità con Spotify: la Track importata valorizza la colonna dedicata
    soundcloud_id (non solo platform_track_id), così il filtro has_soundcloud
    su /api/tracks e il campo serializzato soundcloud_id funzionano."""
    from app.models import Track
    from app.repositories import list_tracks

    import_selected_soundcloud_likes(db, [_entry(1)], ["1001"])
    track = db.query(Track).filter(Track.platform == "soundcloud").one()
    assert track.soundcloud_id == "1001"
    assert track.platform_track_id == "1001"
    # il filtro has_soundcloud (repositories) ora trova la traccia importata
    total, found = list_tracks(db, has_soundcloud=True)
    assert total == 1
    assert found[0].id == track.id
