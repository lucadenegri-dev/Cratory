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
    def fake_extract(url, *, limit=None, flat=True):
        return _info(iter([_entry(1), _entry(2)]))  # generatore: va materializzato

    monkeypatch.setattr(sc, "_extract", fake_extract)
    info = fetch_playlist("https://soundcloud.com/digger/sets/deep-crate")
    assert isinstance(info["entries"], list)
    assert len(info["entries"]) == 2


def test_fetch_playlist_usa_estrazione_piena(monkeypatch):
    # L'import playlist vuole i metadati pieni (uploader/durata), non il flat.
    seen = {}

    def fake_extract(url, *, limit=None, flat=True):
        seen["flat"] = flat
        return _info([_entry(1)])

    monkeypatch.setattr(sc, "_extract", fake_extract)
    fetch_playlist("https://soundcloud.com/digger/sets/deep-crate")
    assert seen["flat"] is False


def test_fetch_likes_costruisce_url_e_passa_il_limit(monkeypatch):
    seen = {}

    def fake_extract(url, *, limit=None, flat=True):
        seen["url"] = url
        seen["limit"] = limit
        seen["flat"] = flat
        return _info([_entry(1)])

    monkeypatch.setattr(sc, "_extract", fake_extract)
    fetch_likes("  @luca ", limit=50)
    assert seen["url"] == "https://soundcloud.com/luca/likes"
    assert seen["limit"] == 50
    assert seen["flat"] is True  # la preview dei like resta flat (veloce)


def test_fetch_likes_filtra_le_playlist_nei_like(monkeypatch):
    # Nei like possono esserci anche playlist (/sets/): non sono tracce.
    def fake_extract(url, *, limit=None, flat=True):
        return _info([
            _entry(1),
            _entry(2, url="https://soundcloud.com/u/sets/una-playlist"),
        ])

    monkeypatch.setattr(sc, "_extract", fake_extract)
    info = fetch_likes("luca")
    assert [e["id"] for e in info["entries"]] == ["1001"]


def test_fetch_likes_senza_username_solleva():
    with pytest.raises(SoundCloudError):
        fetch_likes("   ")


def test_fetch_track_estrazione_piena_e_url_validato(monkeypatch):
    seen = {}

    def fake_extract(url, *, limit=None, flat=True):
        seen["flat"] = flat
        return {"id": "77", "title": "T", "uploader": "U"}

    monkeypatch.setattr(sc, "_extract", fake_extract)
    e = sc.fetch_track("https://soundcloud.com/u/track")
    assert e["id"] == "77"
    assert seen["flat"] is False
    with pytest.raises(SoundCloudInvalidUrl):
        sc.fetch_track("https://example.com/x")


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


def test_split_scarta_prefisso_posizione_vinile():
    # "a1 - Pariah - Caterpillar": la posizione della tracklist non è un artista
    assert split_artist_title("a1 - Pariah - Caterpillar (VOAM009)", "Voam") == (
        "Pariah", "Caterpillar (VOAM009)",
    )
    assert split_artist_title("01 - Artist - Track", None) == ("Artist", "Track")
    # prefisso senza secondo separatore: resta solo il titolo, artista dall'uploader
    assert split_artist_title("B2 - Some Track", "chan") == ("chan", "Some Track")


def test_split_inverte_quando_la_destra_matcha_uploader():
    # Convenzione "Titolo - Artista": la destra coincide con chi ha caricato
    assert split_artist_title("Atmosphera - Fabz & Viruks", "Fabz") == (
        "Fabz & Viruks", "Atmosphera",
    )
    assert split_artist_title("Old-fashioned - JAVB DJ", "JAVB") == (
        "JAVB DJ", "Old-fashioned",
    )


def test_split_non_inverte_quando_la_sinistra_matcha_uploader():
    assert split_artist_title("Mi Figue Mi Goyave - To The Moon", "Mi Figue Mi Goyave") == (
        "Mi Figue Mi Goyave", "To The Moon",
    )
    assert split_artist_title("FROND - Anx [Open Culture]", "FROND") == (
        "FROND", "Anx [Open Culture]",
    )


def test_split_nessun_match_uploader_resta_normale():
    # uploader = label/canale terzo: la convenzione "Artista - Titolo" vince
    assert split_artist_title("Grooveyard - Watch Me Now", "Secret Cinema") == (
        "Grooveyard", "Watch Me Now",
    )
    # uploader troppo corto per un match affidabile: nessuna inversione
    assert split_artist_title("Ambient - DJ", "DJ") == ("Ambient", "DJ")


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


def test_normalize_preferisce_pagina_pubblica_allo_stream_cdn():
    """entry['url'] dalla flat extraction e' spesso lo stream CDN temporaneo
    (media-streaming.soundcloud.cloud), non la pagina pubblica: webpage_url va
    preferito quando presente."""
    norm = normalize_soundcloud_item(_entry(
        1,
        url="https://playback.media-streaming.soundcloud.cloud/59BCuNpfI0",
        webpage_url="https://soundcloud.com/digger/cool-track",
    ))
    assert norm.url == "https://soundcloud.com/digger/cool-track"


def test_normalize_url_none_se_resta_solo_lo_stream_cdn():
    """Nessun candidato punta a una pagina soundcloud.com: meglio nessun link
    che uno stream temporaneo/rotto."""
    norm = normalize_soundcloud_item(_entry(
        1, url="https://playback.media-streaming.soundcloud.cloud/59BCuNpfI0",
    ))
    assert norm.url is None


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


def test_preview_mostra_titolo_grezzo_e_utente_dallo_slug(db):
    """La preview rispecchia SoundCloud: titolo com'è + utente che ha caricato
    (dallo slug dell'URL, il display name non c'è in flat mode). Nessun parsing
    artista/titolo: quello avviene all'import."""
    entries = [
        _entry(1, title="a1 - Pariah - Caterpillar (VOAM009)",
               url="https://soundcloud.com/voamlabel/a1-pariah-caterpillar"),
        _entry(2, title="MARECHIARO 9",
               url="https://soundcloud.com/bruno-ruotolo-711086630/marechiaro-9-10"),
    ]
    preview = preview_soundcloud_likes(db, entries)
    assert preview[0]["title"] == "a1 - Pariah - Caterpillar (VOAM009)"  # grezzo, non splittato
    assert preview[0]["uploader"] == "voamlabel"
    assert preview[1]["uploader"] == "bruno ruotolo"  # slug ripulito: via dash e suffisso numerico
    assert "artist" not in preview[0]


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
    assert found[0][0].id == track.id
