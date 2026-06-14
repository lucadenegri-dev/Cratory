"""Test Discovery mode (Fase F) — nessuna rete: similarity, resolver e LLM finti."""

from app.integrations.lastfm import LastFMClient
from app.services.discovery import discover_for_gap, discover_for_playlist


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


def test_lastfm_top_tags_parsing():
    payload = {"toptags": {"tag": [
        {"name": "techno", "count": 100},
        {"name": "dark", "count": 40},
    ]}}
    client = LastFMClient("KEY", http=_FakeHttp(payload))
    assert client.top_tags("Artist", "Title") == ["techno", "dark"]


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
        "album": {"images": [{"url": "http://img/cover.jpg"}]},
        "external_ids": {"isrc": isrc},
        "duration_ms": 240000,
        "artists": [{"name": "NewBand"}],
    }


def _make_playlist(db, rows):
    """rows: lista di dict con almeno artist/title; ritorna il playlist_id."""
    from app.models import Playlist, Track

    pl = Playlist(platform="spotify", name="Test Playlist", kind="playlist")
    db.add(pl)
    db.flush()
    for r in rows:
        db.add(Track(
            source_type="spotify", platform="spotify",
            playlist_id=pl.id, playlist_name=pl.name,
            status="ready_for_set", **r,
        ))
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
    # ranking: il segnale piu' forte (match 0.9) in cima, compatibilita' coerente
    top = result.candidates[0]
    assert top.title == "Fresh Cut"
    assert top.compatibility == 90


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


def test_gap_genre_uses_tags(db):
    pid = _make_playlist(db, [
        {"artist": "Artist 0", "title": "Song A", "genre": "house"},
        {"artist": "Artist 1", "title": "Song B", "genre": "house"},
    ])
    gap = {"gap_type": "low_genre_variety", "description": "un genere domina", "suggestion": ""}
    llm = FakeLLM()
    result = discover_for_gap(db, gap, similarity=FakeSimilarity(), llm=llm, playlist_id=pid, limit=10)
    assert result.mode == "gap"
    # il candidato da tag e' presente (discovery per genere)
    assert any(c.title == "Genre Anthem" for c in result.candidates)
    assert llm.last_payload["gap"]["gap_type"] == "low_genre_variety"
