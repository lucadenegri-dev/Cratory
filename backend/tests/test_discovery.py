"""Test Discovery mode (Fase F) — nessuna rete: similarity, resolver e LLM finti."""

import pytest

from app.integrations.lastfm import LastFMClient
from app.services.discovery import discover_for_playlist


# --- parsing Last.fm (senza rete) --------------------------------------------


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


class _FakeHttp:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResp(self.payload)


def test_lastfm_similar_artists_parsing():
    payload = {"similarartists": {"artist": [
        {"name": "Boards of Canada", "match": "1.0"},
        {"name": "Bonobo", "match": "0.42"},
    ]}}
    client = LastFMClient("KEY", http=_FakeHttp(payload))
    out = client.similar_artists("Aphex Twin")
    assert out == [
        {"name": "Boards of Canada", "match": 1.0},
        {"name": "Bonobo", "match": 0.42},
    ]
    assert client.http.calls[0][1]["api_key"] == "KEY"


def test_lastfm_normalizes_single_dict():
    """Last.fm restituisce un dict (non lista) quando c'e' un solo risultato."""
    payload = {"similartracks": {"track": {
        "name": "Xtal", "artist": {"name": "Aphex Twin"}, "match": "0.8",
    }}}
    client = LastFMClient("KEY", http=_FakeHttp(payload))
    out = client.similar_tracks("Aphex Twin", "Ageispolis")
    assert out == [{"artist": "Aphex Twin", "title": "Xtal", "match": 0.8}]


# --- similarity finta per il servizio ----------------------------------------


class FakeSimilarity:
    name = "fake"

    def __init__(self):
        self.similar_artists_map = {"Artist 0": [{"name": "NewBand", "match": 0.9}]}
        self.top_tracks_map = {"NewBand": [{"artist": "NewBand", "title": "Fresh Cut"}]}
        self.similar_tracks_list = [{"artist": "OtherBand", "title": "Deep Groove", "match": 0.7}]
        self.tag_tracks = [{"artist": "TagBand", "title": "Genre Anthem"}]

    def similar_artists(self, artist, *, limit=20):
        return self.similar_artists_map.get(artist, [])

    def similar_tracks(self, artist, title, *, limit=20):
        return self.similar_tracks_list

    def artist_top_tracks(self, artist, *, limit=10):
        return self.top_tracks_map.get(artist, [])

    def top_tracks_by_tag(self, tag, *, limit=20):
        return self.tag_tracks


class FakeLLM:
    def __init__(self):
        self.last_payload = None

    def complete_json(self, system_prompt, payload, schema):
        self.last_payload = payload
        return {"explanations": [
            {"index": c["index"], "text": f"perche {c['title']}"}
            for c in payload["candidates"]
        ]}


def _spotify_item(track_id="sp1", isrc="USNEW0000001"):
    return {
        "id": track_id,
        "name": "Fresh Cut",
        "external_urls": {"spotify": f"https://open.spotify.com/track/{track_id}"},
        "album": {"id": "alb1", "images": [{"url": "http://img/cover.jpg"}]},
        "external_ids": {"isrc": isrc},
        "duration_ms": 240000,
        "artists": [{"name": "NewBand"}],
    }


def _label_item(track_id, artist, title, *, isrc=None, release_date="2024-01-01"):
    """Item Spotify (forma /search) per il Radar Etichette: gia' 'risolto'."""
    return {
        "id": track_id,
        "name": title,
        "artists": [{"name": artist}],
        "external_urls": {"spotify": f"https://open.spotify.com/track/{track_id}"},
        "album": {"id": f"alb-{track_id}", "images": [{"url": "http://img"}], "release_date": release_date},
        "external_ids": {"isrc": isrc} if isrc else {},
        "duration_ms": 200000,
    }


def _lib_track(db, **kw):
    from app.models import Track

    kw.setdefault("source_type", "spotify")
    t = Track(**kw)
    db.add(t)
    db.commit()
    return t


def _make_playlist(db, rows):
    """rows: lista di dict con almeno artist/title; ritorna il playlist_id."""
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist

    pl = Playlist(platform="spotify", name="Test Playlist", kind="playlist")
    db.add(pl)
    db.flush()
    for r in rows:
        t = Track(source_type="spotify", platform="spotify", status="ready_for_set", **r)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl)
    db.commit()
    return pl.id


def test_expand_collects_and_ranks(db):
    pid = _make_playlist(db, [
        {"artist": "Artist 0", "title": "Song A", "bpm": 128.0, "genre": "techno"},
        {"artist": "Artist 0", "title": "Song B", "bpm": 126.0, "genre": "techno"},
    ])
    sim = FakeSimilarity()
    result = discover_for_playlist(db, pid, similarity=sim, limit=10)

    titles = {c.title for c in result.candidates}
    assert "Fresh Cut" in titles      # via similar_artist -> top track
    assert "Deep Groove" in titles    # via similar_track
    assert result.mode == "expand"
    assert result.scope == "Test Playlist"
    # ranking: il segnale piu' forte (match 0.9) in cima
    top = result.candidates[0]
    assert top.title == "Fresh Cut"
    assert top.match == 0.9


def test_expand_drops_tracks_already_in_library(db):
    # "Deep Groove" di OtherBand e' gia' in libreria: non deve essere suggerita.
    pid = _make_playlist(db, [
        {"artist": "Artist 0", "title": "Song A"},
        {"artist": "OtherBand", "title": "Deep Groove"},
    ])
    result = discover_for_playlist(db, pid, similarity=FakeSimilarity(), limit=10)
    assert all(not (c.artist == "OtherBand" and c.title == "Deep Groove") for c in result.candidates)


def test_resolver_fills_spotify_fields(db):
    pid = _make_playlist(db, [{"artist": "Artist 0", "title": "Song A"}])

    def resolve(artist, title):
        return _spotify_item() if title == "Fresh Cut" else None

    result = discover_for_playlist(db, pid, similarity=FakeSimilarity(), resolve=resolve, limit=10)
    fresh = next(c for c in result.candidates if c.title == "Fresh Cut")
    assert fresh.spotify_id == "sp1"
    assert fresh.album_art_url == "http://img/cover.jpg"
    assert fresh.isrc == "USNEW0000001"
    assert fresh.duration_seconds == 240
    # le tracce risolvibili vengono prima delle non risolvibili
    assert result.candidates[0].resolved


def test_resolver_dedup_by_isrc(db):
    # In libreria c'e' gia' una traccia con lo stesso ISRC che il resolver assegna.
    pid = _make_playlist(db, [
        {"artist": "Artist 0", "title": "Song A"},
        {"artist": "Whoever", "title": "Owned", "isrc": "USNEW0000001"},
    ])

    def resolve(artist, title):
        return _spotify_item() if title == "Fresh Cut" else None

    result = discover_for_playlist(db, pid, similarity=FakeSimilarity(), resolve=resolve, limit=10)
    assert all(c.title != "Fresh Cut" for c in result.candidates)  # scartata per ISRC


def test_ai_explanations_merged(db):
    pid = _make_playlist(db, [{"artist": "Artist 0", "title": "Song A"}])
    llm = FakeLLM()
    result = discover_for_playlist(db, pid, similarity=FakeSimilarity(), llm=llm, limit=10)
    assert all(c.explanation for c in result.candidates)
    assert llm.last_payload["playlist_profile"]["track_count"] == 1


def test_add_discovered_track_to_library(db):
    from app.models import Track
    from app.services.playlist_import import import_single_track

    track, created = import_single_track(
        db, platform="spotify", platform_track_id="sp1", title="Fresh Cut",
        artist="NewBand", isrc="USNEW0000001", duration_seconds=240, artwork_url="http://img",
    )
    assert created is True
    assert track.id is not None
    assert track.spotify_id == "sp1"
    assert track.source_type == "spotify"
    assert track.playlist_id is None  # entra in libreria, non legata a una playlist

    # idempotente: stesso ISRC -> stessa traccia, nessun duplicato
    again, created2 = import_single_track(
        db, platform="spotify", platform_track_id="sp1", title="Fresh Cut",
        artist="NewBand", isrc="USNEW0000001",
    )
    assert created2 is False
    assert again.id == track.id
    assert db.query(Track).count() == 1


def test_resolution_is_bounded(db):
    """Anche con centinaia di candidati, il resolver Spotify è chiamato un numero limitato di volte."""
    from app.services.discovery import RESOLVE_BUFFER

    pid = _make_playlist(db, [{"artist": "Artist 0", "title": "Seed"}])

    class ManySimilarity(FakeSimilarity):
        def similar_artists(self, artist, *, limit=20):
            return []

        def similar_tracks(self, artist, title, *, limit=20):
            return [{"artist": f"A{i}", "title": f"T{i}", "match": 0.9 - i * 0.001} for i in range(100)]

    calls = {"n": 0}

    def resolve(artist, title):
        calls["n"] += 1
        return None

    limit = 5
    result = discover_for_playlist(db, pid, similarity=ManySimilarity(), resolve=resolve, limit=limit)
    assert calls["n"] <= limit + RESOLVE_BUFFER
    assert len(result.candidates) == limit


def test_add_unresolved_track_dedup_by_name(db):
    """Un candidato senza ISRC/spotify_id aggiunto due volte non duplica (match per nome)."""
    from app.models import Track
    from app.services.playlist_import import import_single_track

    t1, c1 = import_single_track(db, platform="manual", title="Untitled", artist="Ghost")
    t2, c2 = import_single_track(db, platform="manual", title="Untitled", artist="Ghost")
    assert c1 is True and c2 is False
    assert t1.id == t2.id
    assert db.query(Track).count() == 1


def test_expand_annotates_owned_label(db):
    pid = _make_playlist(db, [{"artist": "Artist 0", "title": "Song A"}])

    def resolve(artist, title):
        return _spotify_item() if title == "Fresh Cut" else None

    def album_label_fn(album_id):
        return "Warp Records" if album_id == "alb1" else None

    result = discover_for_playlist(
        db, pid, similarity=FakeSimilarity(), resolve=resolve,
        album_label_fn=album_label_fn, owned_labels={"warp records"}, limit=10,
    )
    fresh = next(c for c in result.candidates if c.title == "Fresh Cut")
    assert fresh.label == "Warp Records"
    assert fresh.label_owned is True


# --- Task 4: router dig — reasons in output, taste_playlist_id in input -------

from app.integrations.discogs import DiscogsClient, DiscogsError
from app.models import Playlist, Track
from app.routers.discovery import dig_endpoint
from app.schemas import DiscoveryDigRequest


def _fake_release(title, *, label="Lbl", style="Acid House", have=3, want=120):
    return {
        "id": 1, "title": title, "year": 2024,
        "label": [label], "style": [style],
        "community": {"have": have, "want": want}, "format": ["Vinyl"],
        "uri": "/release/1", "cover_image": "http://img",
    }


def test_dig_endpoint_returns_reasons(db, monkeypatch):
    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [_fake_release("Cult - Grail")],
    )
    resp = dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    assert resp.leads, "atteso almeno un lead"
    codes = {r.code for r in resp.leads[0].reasons}
    assert "rare_wanted" in codes and "deep_cut" in codes


def test_format_badge_priority():
    from app.services.discovery_dig import _format_badge

    assert _format_badge({"vinyl", "ep"}) == "EP"
    assert _format_badge({"vinyl", "lp", "album"}) == "LP"  # LP ha priorità su Album
    assert _format_badge({"vinyl", "12\""}) == '12"'
    assert _format_badge({"vinyl"}) is None
    assert _format_badge(set()) is None
    # Regressione: match ESATTO, non per sostringa. Una ristampa LP ha il
    # descrittore "repress" che CONTIENE "ep" — non deve diventare "EP".
    assert _format_badge({"vinyl", "lp", "album", "repress"}) == "LP"


def test_dig_endpoint_exposes_discogs_id_and_format_badge(db, monkeypatch):
    release = {
        "id": 42, "title": "Cult - Grail", "year": 2024,
        "label": ["Lbl"], "style": ["Acid House"],
        "community": {"have": 3, "want": 120}, "format": ["Vinyl", "EP"],
        "uri": "/release/42", "cover_image": "http://img",
    }
    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [release],
    )
    resp = dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    lead = resp.leads[0]
    assert lead.discogs_id == 42
    assert lead.format_badge == "EP"


def test_dig_endpoint_honors_taste_playlist_id(db, monkeypatch):
    from app.repositories import add_track_to_playlist
    pl = Playlist(platform="spotify", name="Peak Time")
    db.add(pl)
    db.flush()
    t = Track(source_type="spotify", artist="Followed", title="Older",
              label="Warp", genre="Acid House")
    db.add(t)
    db.flush()
    add_track_to_playlist(db, t, pl)
    db.commit()

    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [_fake_release("Followed - New", label="Warp", style="Acid House")],
    )
    resp = dig_endpoint(
        DiscoveryDigRequest(seed_type="genre", value="Acid House", taste_playlist_id=pl.id),
        db,
    )
    codes = {r.code for r in resp.leads[0].reasons}
    assert {"label_followed", "artist_collected", "style_match"} <= codes


def test_dig_endpoint_502_on_discogs_error(db, monkeypatch):
    """Rate limit o token mancante NON devono sembrare 'zero risultati': il dig
    traduce DiscogsError in un 502 esplicito (stesso codice di get_release_detail,
    gia' tradotto dal frontend)."""
    from fastapi import HTTPException

    def _raise(self, **kw):
        raise DiscogsError("Discogs: rate limit (riprova piu' tardi o imposta DISCOGS_TOKEN).")

    monkeypatch.setattr(DiscogsClient, "search_releases", _raise)
    with pytest.raises(HTTPException) as exc_info:
        dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["code"] == "discovery_provider_error"


# --- Task 3: GET /api/discovery/release/{discogs_id} — tracklist reale -------

_RELEASE_DETAIL = {
    "id": 249504,
    "title": "Selected Ambient Works 85-92",
    "artists": [{"name": "Aphex Twin (2)"}],
    "year": 1992,
    "labels": [{"name": "Apollo"}],
    "images": [{"type": "primary", "uri": "http://img/cover.jpg"}],
    "tracklist": [
        {"position": "A1", "type_": "track", "title": "Xtal", "duration": "4:56"},
        {"position": "", "type_": "heading", "title": "Side B"},
        {"position": "B1", "type_": "track", "title": "Tha", "duration": "4:35"},
        {"position": "B2", "type_": "track", "title": "Untitled", "duration": ""},
    ],
    "uri": "https://www.discogs.com/release/249504-Aphex-Twin-Selected-Ambient-Works-85-92",
}


def test_release_detail_normalizes_tracklist(db, monkeypatch):
    from app.routers.discovery import get_release_detail

    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: _RELEASE_DETAIL)
    out = get_release_detail(249504)
    assert out.discogs_id == 249504
    assert out.title == "Selected Ambient Works 85-92"
    assert out.artist == "Aphex Twin"  # suffisso di disambiguazione Discogs "(2)" rimosso
    assert out.label == "Apollo"
    assert out.thumb_url == "http://img/cover.jpg"
    assert out.discogs_url == _RELEASE_DETAIL["uri"]
    # la voce "heading" (Side B) e' esclusa: non e' una traccia
    assert [t.title for t in out.tracks] == ["Xtal", "Tha", "Untitled"]
    assert out.tracks[0].duration_seconds == 296  # "4:56" -> 4*60+56
    assert out.tracks[2].duration_seconds is None  # durata vuota -> None


def test_release_detail_502_on_discogs_error(monkeypatch):
    from fastapi import HTTPException
    from app.routers.discovery import get_release_detail

    def _raise(self, rid):
        raise DiscogsError("Discogs 500: boom")
    monkeypatch.setattr(DiscogsClient, "get_release", _raise)
    with pytest.raises(HTTPException) as exc_info:
        get_release_detail(249504)
    assert exc_info.value.status_code == 502


def test_release_detail_tolerates_image_and_label_without_keys(monkeypatch):
    """Un'immagine/etichetta Discogs priva della chiave attesa non deve far
    esplodere l'endpoint con un 500 grezzo: thumb_url/label degradano a None."""
    from app.routers.discovery import get_release_detail

    payload = {
        "id": 1, "title": "Rel", "artists": [{"name": "A"}],
        "images": [{"type": "primary"}],   # nessun "uri"
        "labels": [{"catno": "X-1"}],        # nessun "name"
        "tracklist": [{"position": "A1", "type_": "track", "title": "T", "duration": "3:00"}],
    }
    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: payload)
    out = get_release_detail(1)
    assert out.thumb_url is None
    assert out.label is None
    assert [t.title for t in out.tracks] == ["T"]


# --- Task 4: playlist di sistema "Scoperte" -----------------------------------


def test_get_or_create_discovery_playlist_is_idempotent(db):
    from app.services.playlist_import import get_or_create_discovery_playlist

    p1 = get_or_create_discovery_playlist(db)
    db.commit()
    p2 = get_or_create_discovery_playlist(db)
    assert p1.id == p2.id
    assert p1.name == "Scoperte"
    assert p1.kind == "discovery"
    assert p1.platform == "manual"


# --- Task 5: POST /api/discovery/save-for-later ------------------------------


def test_save_for_later_imports_and_adds_to_discovery_playlist(db):
    from app.routers.discovery import save_for_later
    from app.schemas import DiscoverySaveForLaterRequest
    from app.services.playlist_import import get_or_create_discovery_playlist
    from app.repositories import tracks_for_playlist

    resp = save_for_later(DiscoverySaveForLaterRequest(
        artist="Voiron", title="Night Signal", duration_seconds=320,
    ), db)
    assert resp.created is True
    assert resp.track.title == "Night Signal"

    playlist = get_or_create_discovery_playlist(db)
    tracks = tracks_for_playlist(db, playlist.id)
    assert [t.title for t in tracks] == ["Night Signal"]

    # idempotente: stessa traccia (match per nome, niente ISRC/platform_track_id),
    # nessuna membership duplicata
    save_for_later(DiscoverySaveForLaterRequest(artist="Voiron", title="Night Signal"), db)
    assert len(tracks_for_playlist(db, playlist.id)) == 1
