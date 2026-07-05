"""Test Fase B: conversione key->Camelot, provider GetSongBPM (parsing senza rete),
factory e guardia del router. Nessuna chiamata HTTP reale.
"""

import pytest
from fastapi import HTTPException

from app.core import config
from app.integrations.getsongbpm import (
    ChainedFeatureProvider,
    FeatureProviderNotConfigured,
    GetSongBPMProvider,
    configured_provider_name,
    feature_provider_configured,
    get_feature_provider,
)
from app.integrations.musicbrainz import MusicBrainzProvider
from app.routers import enrichment
from app.services.camelot import pitch_to_camelot


# --- key musicale -> Camelot --------------------------------------------------


def test_pitch_to_camelot_major_minor():
    assert pitch_to_camelot("C") == "8B"        # C maggiore
    assert pitch_to_camelot("Am") == "8A"       # relativa minore
    assert pitch_to_camelot("C#m") == "12A"
    assert pitch_to_camelot("Db") == "3B"       # enarmonico di C#
    assert pitch_to_camelot("F# minor") == "11A"
    assert pitch_to_camelot("Bbm") == "3A"
    assert pitch_to_camelot("G") == "9B"
    assert pitch_to_camelot("Emin") == "9A"
    assert pitch_to_camelot("Gm") == "6A"


def test_pitch_to_camelot_invalid():
    assert pitch_to_camelot("") is None
    assert pitch_to_camelot(None) is None
    assert pitch_to_camelot("8A") is None       # gia' Camelot: non e' compito di questa funzione
    assert pitch_to_camelot("xyz") is None


# --- parsing GetSongBPM (senza rete) -----------------------------------------


def test_parse_song_maps_fields():
    p = GetSongBPMProvider("KEY")
    song = {"title": "Track", "artist": {"name": "Artist"},
            "tempo": "124", "key_of": "Am", "danceability": "77"}
    out = p._parse_song(song, artist="Artist")
    assert out["bpm"] == 124.0
    assert out["camelot_key"] == "8A"
    assert out["danceability"] == 77
    assert out["confidence"] == 80


def test_parse_song_partial_and_empty():
    p = GetSongBPMProvider("KEY")
    assert p._parse_song({"tempo": ""}, artist=None) is None  # nessun dato utile
    out = p._parse_song({"tempo": "120", "key_of": "???"}, artist=None)
    assert out["bpm"] == 120.0
    assert "camelot_key" not in out          # key non interpretabile -> non inventata
    assert out["confidence"] == 55


def test_best_match_prefers_artist():
    p = GetSongBPMProvider("KEY")
    results = [
        {"title": "X", "artist": {"name": "Other"}, "tempo": "100"},
        {"title": "X", "artist": {"name": "Daft Punk"}, "tempo": "123"},
    ]
    assert p._best_match(results, "X", "Daft Punk")["tempo"] == "123"


def test_lookup_candidates_clean_versions_and_primary_artist():
    p = GetSongBPMProvider("KEY")
    candidates = p._lookup_candidates(
        title="Starlight - Extended Mix",
        artist="Danny L Harle, PinkPantheress",
    )
    assert candidates[0].source == "original"
    assert any(c.title == "Starlight" for c in candidates)
    assert any(c.artist == "Danny L Harle" for c in candidates)


def test_best_match_uses_fuzzy_artist_and_duration():
    p = GetSongBPMProvider("KEY")
    results = [
        {"title": "Starlight", "artist": {"name": "Other"}, "tempo": "124", "duration": 180},
        {"title": "Starlight - Extended Mix", "artist": {"name": "Danny L Harle"}, "tempo": "128", "duration": 240},
    ]
    best = p._best_match(results, "Starlight", "Danny L Harle", duration_seconds=240)
    assert best["tempo"] == "128"


# --- lookup end-to-end con http finto ----------------------------------------


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


class _QueuedHttp:
    def __init__(self, payloads):
        self.payloads, self.calls = list(payloads), []

    def get(self, url, params=None):
        self.calls.append((url, params))
        payload = self.payloads.pop(0) if self.payloads else {"search": []}
        return _FakeResp(payload)


def test_lookup_end_to_end_no_network():
    payload = {"search": [
        {"title": "Da Funk", "artist": {"name": "Daft Punk"},
         "tempo": "112", "key_of": "Gm", "danceability": "60"},
    ]}
    http = _FakeHttp(payload)
    p = GetSongBPMProvider("KEY", http=http)
    out = p.lookup(title="Da Funk", artist="Daft Punk")
    assert out["bpm"] == 112.0
    assert out["camelot_key"] == "6A"  # Gm
    assert out["confidence"] == 85
    assert http.calls and http.calls[0][1]["api_key"] == "KEY"


def test_lookup_retries_clean_candidate_no_network():
    http = _QueuedHttp([
        {"search": []},
        {"search": [
            {"title": "Track", "artist": {"name": "DJ, Singer"}, "tempo": "126", "key_of": "Am"},
        ]},
    ])
    p = GetSongBPMProvider("KEY", http=http)
    out = p.lookup(title="Track - Extended Mix", artist="DJ, Singer")
    assert out["bpm"] == 126.0
    assert out["camelot_key"] == "8A"
    assert out["lookup_source"] == "clean_title"
    assert out["lookup_attempts"] == 2
    assert len(http.calls) == 2
    assert http.calls[1][1]["lookup"] == "song:Track artist:DJ, Singer"


def test_lookup_no_results():
    p = GetSongBPMProvider("KEY", http=_FakeHttp({"search": {"error": "no result"}}))
    assert p.lookup(title="Nope", artist="Nobody") is None
    assert p.lookup(title=None, artist="x") is None


# --- factory + guardia router ------------------------------------------------


def _only_keyed_providers(monkeypatch):
    """Disattiva i provider zero-config (Deezer/AcousticBrainz) per isolare i test
    sui provider con chiave/credenziale."""
    monkeypatch.setattr(config.settings, "deezer_enabled", False, raising=False)
    monkeypatch.setattr(config.settings, "acousticbrainz_enabled", False, raising=False)


def test_factory_requires_config(monkeypatch):
    _only_keyed_providers(monkeypatch)
    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "", raising=False)
    monkeypatch.setattr(config.settings, "musicbrainz_user_agent", "", raising=False)
    monkeypatch.setattr(config.settings, "lastfm_api_key", "", raising=False)
    assert feature_provider_configured() is False
    with pytest.raises(FeatureProviderNotConfigured):
        get_feature_provider()

    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "abc", raising=False)
    assert feature_provider_configured() is True
    assert get_feature_provider().name == "getsongbpm"


def test_router_guard_and_status(monkeypatch):
    _only_keyed_providers(monkeypatch)
    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "", raising=False)
    monkeypatch.setattr(config.settings, "musicbrainz_user_agent", "", raising=False)
    monkeypatch.setattr(config.settings, "lastfm_api_key", "", raising=False)
    with pytest.raises(HTTPException) as ei:
        enrichment.enrich(force=False)
    assert ei.value.status_code == 409
    assert enrichment.status()["configured"] is False

    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "abc", raising=False)
    assert enrichment.status() == {"configured": True, "provider": "getsongbpm"}


def test_deezer_enabled_alone_makes_enrichment_configured(monkeypatch):
    """Deezer e' zero-config (BPM via ISRC): da solo rende l'enrichment disponibile."""
    monkeypatch.setattr(config.settings, "deezer_enabled", True, raising=False)
    monkeypatch.setattr(config.settings, "acousticbrainz_enabled", False, raising=False)
    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "", raising=False)
    monkeypatch.setattr(config.settings, "musicbrainz_user_agent", "", raising=False)
    monkeypatch.setattr(config.settings, "lastfm_api_key", "", raising=False)
    assert feature_provider_configured() is True
    assert get_feature_provider().name == "deezer"
    assert configured_provider_name() == "deezer"


# --- MusicBrainz (parsing senza rete) ----------------------------------------


def test_musicbrainz_parse_recording():
    p = MusicBrainzProvider("Cratory/1.0 (test)")
    rec = {
        "title": "Track", "score": 90,
        "releases": [{"date": "2009-05-01", "label-info": [{"label": {"name": "Kompakt"}}]}],
        "tags": [{"name": "techno", "count": 5}, {"name": "minimal", "count": 2}],
    }
    out = p._parse_recording(rec, isrc="DEXXX0900001", exact=True)
    assert out["label"] == "Kompakt"
    assert out["release_date"] == "2009-05-01"
    assert out["genre_primary"] == "techno"
    assert out["isrc"] == "DEXXX0900001"
    assert out["confidence"] == 95


def test_musicbrainz_parse_recording_empty():
    p = MusicBrainzProvider("ua")
    assert p._parse_recording({"score": 50}, isrc=None, exact=False) is None


def test_musicbrainz_lookup_diretto_con_mbid_nel_context():
    """Con l'mbid nel context (fingerprinting): GET /recording/{mbid}, niente search fuzzy."""
    recording = {
        "id": "mbid-1", "title": "Track",
        "releases": [{"date": "2019-03-01", "label-info": [{"label": {"name": "Afterlife"}}]}],
        "tags": [{"name": "melodic techno", "count": 4}],
    }
    http = _FakeHttp(recording)
    p = MusicBrainzProvider("ua", http=http)
    p._MIN_INTERVAL = 0
    out = p.lookup(title="X", artist="Y", context={"mbid": "mbid-1"})
    assert out["label"] == "Afterlife"
    assert out["genre_primary"] == "melodic techno"
    assert out["confidence"] == 95  # identita' certa via mbid
    assert len(http.calls) == 1
    assert "/recording/mbid-1" in http.calls[0][0]


def test_musicbrainz_mbid_fallito_fallback_su_search():
    """Se il lookup per mbid fallisce (es. 404), si torna al percorso ISRC/search."""
    search_payload = {"recordings": [
        {"id": "mbid-2", "title": "Track", "score": 90,
         "releases": [{"date": "2020-01-01"}], "tags": [{"name": "techno", "count": 2}]},
    ]}

    class _MixedHttp:
        def __init__(self):
            self.calls = []

        def get(self, url, params=None):
            self.calls.append((url, params))
            if "/recording/mbid-x" in url:
                return _FakeResp({"error": "not found"}, status=404)
            return _FakeResp(search_payload)

    http = _MixedHttp()
    p = MusicBrainzProvider("ua", http=http)
    p._MIN_INTERVAL = 0
    out = p.lookup(title="Track", artist="Y", context={"mbid": "mbid-x"})
    assert out["genre_primary"] == "techno"
    assert len(http.calls) == 2  # mbid fallito -> search


def test_enrich_features_passa_mbid_nel_context(db):
    """Le tracce con mbid (fingerprinting) lo espongono alla catena via context."""
    from app.models import Track
    from app.services.feature_enrichment import enrich_features

    class Capture:
        name = "cap"

        def __init__(self):
            self.contexts = []

        def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
            self.contexts.append(context)
            return None

    with_mbid = Track(source_type="local_files", title="T1", artist="A", mbid="mbid-locale")
    without = Track(source_type="spotify", title="T2", artist="B")
    db.add_all([with_mbid, without])
    db.commit()
    prov = Capture()
    enrich_features(db, prov, force=True, track_ids=[with_mbid.id, without.id])
    assert prov.contexts == [{"mbid": "mbid-locale"}, None]


def test_musicbrainz_best_recording_prefers_match():
    p = MusicBrainzProvider("ua")
    recs = [
        {"title": "Other", "score": 50, "artist-credit": [{"name": "X"}]},
        {"title": "Da Funk", "score": 80, "artist-credit": [{"name": "Daft Punk"}]},
    ]
    assert p._best_recording(recs, "Da Funk", "Daft Punk")["title"] == "Da Funk"


# --- catena di provider ------------------------------------------------------


class _Stub:
    def __init__(self, name, data):
        self.name, self._data = name, data

    def lookup(self, **kw):
        return self._data


def test_chain_first_wins_and_max_confidence():
    a = _Stub("a", {"bpm": 124.0, "camelot_key": "8A", "confidence": 80})
    b = _Stub("b", {"camelot_key": "9A", "label": "Kompakt", "genre_primary": "techno", "confidence": 95})
    out = ChainedFeatureProvider([a, b]).lookup(title="t", artist="x")
    assert out["bpm"] == 124.0
    assert out["camelot_key"] == "8A"      # primo provider vince
    assert out["label"] == "Kompakt"        # completato dal secondo
    assert out["genre_primary"] == "techno"
    assert out["confidence"] == 95          # massima


def test_chain_retries_getsongbpm_with_canonical_metadata():
    class _GetSong:
        name = "getsongbpm"

        def __init__(self):
            self.calls = []

        def lookup(self, *, title, artist, **_):
            self.calls.append((title, artist))
            if title == "Canonical Title" and artist == "Canonical Artist":
                return {"bpm": 130.0, "camelot_key": "9A", "confidence": 85}
            return None

    normalizer = _Stub("musicbrainz", {
        "canonical_title": "Canonical Title",
        "canonical_artist": "Canonical Artist",
        "confidence": 90,
    })
    getsong = _GetSong()
    out = ChainedFeatureProvider([getsong, normalizer]).lookup(title="Messy", artist="Feat Artist")
    assert out["bpm"] == 130.0
    assert out["camelot_key"] == "9A"
    assert out["canonical_retry"] is True
    assert getsong.calls == [("Messy", "Feat Artist"), ("Canonical Title", "Canonical Artist")]


def test_chain_returns_none_if_all_empty():
    chain = ChainedFeatureProvider([_Stub("a", None), _Stub("b", None)])
    assert chain.lookup(title="t", artist=None) is None


def test_factory_builds_chain_when_both_configured(monkeypatch):
    _only_keyed_providers(monkeypatch)
    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "k", raising=False)
    monkeypatch.setattr(config.settings, "musicbrainz_user_agent", "ua", raising=False)
    monkeypatch.setattr(config.settings, "lastfm_api_key", "", raising=False)
    assert get_feature_provider().name == "chain"
    assert configured_provider_name() == "musicbrainz + getsongbpm"

    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "", raising=False)
    assert get_feature_provider().name == "musicbrainz"


def test_factory_chain_order_with_all_free_providers(monkeypatch):
    """Catena completa: Deezer -> MusicBrainz -> AcousticBrainz -> GetSongBPM -> Last.fm."""
    monkeypatch.setattr(config.settings, "deezer_enabled", True, raising=False)
    monkeypatch.setattr(config.settings, "acousticbrainz_enabled", True, raising=False)
    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "k", raising=False)
    monkeypatch.setattr(config.settings, "musicbrainz_user_agent", "ua", raising=False)
    monkeypatch.setattr(config.settings, "lastfm_api_key", "lf", raising=False)
    provider = get_feature_provider()
    assert provider.name == "chain"
    assert [p.name for p in provider.providers] == [
        "deezer", "musicbrainz", "acousticbrainz", "getsongbpm", "lastfm",
    ]
    assert configured_provider_name() == "deezer + musicbrainz + acousticbrainz + getsongbpm + lastfm"


def test_factory_skips_acousticbrainz_without_musicbrainz(monkeypatch):
    """AcousticBrainz e' indicizzato per MBID: senza MusicBrainz non entra in catena."""
    monkeypatch.setattr(config.settings, "deezer_enabled", True, raising=False)
    monkeypatch.setattr(config.settings, "acousticbrainz_enabled", True, raising=False)
    monkeypatch.setattr(config.settings, "getsongbpm_api_key", "", raising=False)
    monkeypatch.setattr(config.settings, "musicbrainz_user_agent", "", raising=False)
    monkeypatch.setattr(config.settings, "lastfm_api_key", "", raising=False)
    assert get_feature_provider().name == "deezer"  # solo Deezer, niente AcousticBrainz


# --- cache enrichment --------------------------------------------------------


class _CountingProvider:
    name = "counting"

    def __init__(self, found: bool = True):
        self.calls = 0
        self._data = {"bpm": 128.0, "camelot_key": "8A", "confidence": 80} if found else None

    def lookup(self, **kw):
        self.calls += 1
        return self._data


def _null_bpm(db):
    from app.models import Track
    for t in db.query(Track).all():
        t.bpm = None
        t.status = "imported"
    db.commit()


def test_cache_populated_after_enrichment(db, seed_tracks):
    """Prima passata: cache popolata con un entry per ogni traccia, zero cache hits."""
    from app.models import EnrichmentCache
    from app.services.feature_enrichment import enrich_features

    seed_tracks(n=5)
    _null_bpm(db)

    p = _CountingProvider()
    r = enrich_features(db, p)
    assert p.calls == 5
    assert r["cache_hits"] == 0
    assert r["enriched"] == 5
    assert r["with_bpm"] == 5
    assert r["with_key"] == 5
    assert r["ready_for_set"] == 5
    assert db.query(EnrichmentCache).count() == 5


def test_enrichment_report_distinguishes_metadata_from_core_features(db):
    from app.models import Track
    from app.services.feature_enrichment import enrich_features

    db.add(Track(source_type="spotify", title="Metadata Only", artist="Artist"))
    db.commit()

    class _MetadataOnlyProvider:
        name = "metadata"

        def lookup(self, **_):
            return {"genre_primary": "techno", "confidence": 90}

    r = enrich_features(db, _MetadataOnlyProvider())
    track = db.query(Track).one()

    assert r["provider_matches"] == 1
    assert r["enriched"] == 1
    assert r["metadata_enriched"] == 1
    assert r["with_bpm"] == 0
    assert r["with_key"] == 0
    assert r["ready_for_set"] == 0
    assert r["missing_core_features"] == 1
    assert r["field_counts"] == {"genre": 1}
    assert track.status == "imported"


def test_cache_serves_subsequent_run(db, seed_tracks):
    """Seconda passata sulle stesse tracce: zero chiamate al provider, dati dalla cache."""
    from app.services.feature_enrichment import enrich_features

    seed_tracks(n=5)
    _null_bpm(db)

    p1 = _CountingProvider()
    enrich_features(db, p1)
    assert p1.calls == 5

    _null_bpm(db)  # reset bpm per ri-elaborare le stesse tracce

    p2 = _CountingProvider()
    r2 = enrich_features(db, p2)
    assert r2["cache_hits"] == 5
    assert p2.calls == 0
    assert r2["enriched"] == 5


def test_cache_stores_not_found(db, seed_tracks):
    """Se il provider non trova la traccia, None viene cachato: nessun retry."""
    from app.services.feature_enrichment import enrich_features

    seed_tracks(n=3)
    _null_bpm(db)

    p1 = _CountingProvider(found=False)
    r1 = enrich_features(db, p1)
    assert p1.calls == 3
    assert r1["not_found"] == 3
    assert r1["cache_hits"] == 0

    # bpm ancora None (not found non lo setta) → ri-elaborate ma dalla cache
    p2 = _CountingProvider(found=False)
    r2 = enrich_features(db, p2)
    assert r2["cache_hits"] == 3
    assert p2.calls == 0
    assert r2["not_found"] == 3


def test_force_bypasses_cache(db, seed_tracks):
    """force=True bypassa la cache in lettura e chiama sempre il provider."""
    from app.services.feature_enrichment import enrich_features

    seed_tracks(n=4)
    _null_bpm(db)

    p1 = _CountingProvider()
    enrich_features(db, p1)
    assert p1.calls == 4

    p2 = _CountingProvider()
    r2 = enrich_features(db, p2, force=True)
    assert p2.calls == 4
    assert r2["cache_hits"] == 0


def test_seleziona_anche_tracce_con_bpm_ma_senza_key(db):
    """Senza force: una traccia con BPM ma senza key entra comunque nel batch.

    Prima la selezione guardava solo `bpm IS NULL`: una traccia rimasta senza
    key (o genere) non veniva mai riprocessata se non con force.
    """
    from app.models import Track
    from app.services.feature_enrichment import enrich_features

    db.add(Track(source_type="spotify", title="Has BPM", artist="A", bpm=126.0))
    db.commit()

    p = _CountingProvider()  # risponde bpm 128 + key 8A
    r = enrich_features(db, p)
    assert p.calls == 1
    assert r["total"] == 1
    track = db.query(Track).one()
    assert track.camelot_key == "8A"   # la key mancante viene completata
    assert track.bpm == 126.0          # il BPM esistente resta autorevole


def test_non_seleziona_tracce_gia_complete(db, seed_tracks):
    """Tracce con BPM e key restano fuori dal batch senza force."""
    from app.services.feature_enrichment import enrich_features

    seed_tracks(n=3)  # bpm e camelot_key gia' valorizzati

    p = _CountingProvider()
    r = enrich_features(db, p)
    assert p.calls == 0
    assert r["total"] == 0


# --- Last.fm tag provider + energy proxy -------------------------------------


def test_lastfm_tag_provider_derives_mood_and_genre():
    from app.integrations.lastfm import LastFmTagProvider

    class _FakeClient:
        def canonical_track(self, artist, title):
            return {"canonical_title": title, "canonical_artist": artist}

        def top_tags(self, artist, title, *, limit=8):
            return ["seen live", "techno", "dark", "2010s"]

    out = LastFmTagProvider(_FakeClient()).lookup(title="X", artist="Y")
    assert out["genre_primary"] == "techno"  # primo tag valido (non junk/mood/decade)
    assert out["mood"] == "dark"
    assert out["canonical_title"] == "X"
    assert out["confidence"] == 45


def test_lastfm_tag_provider_none_without_useful_tags():
    from app.integrations.lastfm import LastFmTagProvider

    class _FakeClient:
        def canonical_track(self, artist, title):
            return None

        def top_tags(self, artist, title, *, limit=8):
            return ["favorites", "seen live"]

    assert LastFmTagProvider(_FakeClient()).lookup(title="X", artist="Y") is None


def test_lastfm_tag_provider_can_return_only_canonical_metadata():
    from app.integrations.lastfm import LastFmTagProvider

    class _FakeClient:
        def canonical_track(self, artist, title):
            return {"canonical_title": "Canonical", "canonical_artist": "Artist"}

        def top_tags(self, artist, title, *, limit=8):
            return []

    out = LastFmTagProvider(_FakeClient()).lookup(title="Typo", artist="Artist")
    assert out["canonical_title"] == "Canonical"
    assert out["canonical_artist"] == "Artist"
    assert out["confidence"] == 35


def test_estimate_energy_proxy():
    from app.services.feature_enrichment import estimate_energy

    assert estimate_energy(None, None, None) is None
    low, high = estimate_energy(118.0, None, None), estimate_energy(138.0, None, None)
    assert 0 <= low <= 100 and 0 <= high <= 100
    assert high > low  # BPM piu' alto -> energia piu' alta
    # bias di genere: techno > ambient a parita' di BPM/danceability
    assert estimate_energy(128.0, 50, "techno") > estimate_energy(128.0, 50, "ambient")


def test_enrichment_fills_energy_proxy(db, seed_tracks):
    """Se il provider dà il BPM ma non l'energia, l'energia viene stimata dal proxy."""
    from app.models import Track
    from app.services.feature_enrichment import enrich_features

    seed_tracks(n=3)
    _null_bpm(db)
    enrich_features(db, _CountingProvider())  # restituisce bpm 128, niente energy
    tracks = db.query(Track).all()
    assert all(t.bpm == 128.0 for t in tracks)
    assert all(t.energy is not None for t in tracks)  # stimata deterministicamente


def test_musicbrainz_si_sospende_dopo_connessioni_troncate(monkeypatch):
    # MusicBrainz (o un middlebox) tronca le connessioni a meta' run: dopo 2
    # fallimenti consecutivi il provider si sospende per il resto del run invece
    # di macinare warning e rallentare la catena (che prosegue con gli altri).
    import httpx

    from app.integrations import _http
    from app.integrations.musicbrainz import MusicBrainzProvider

    monkeypatch.setattr(_http.time, "sleep", lambda s: None)  # niente backoff reale

    class DeadHttp:
        def __init__(self):
            self.calls = 0

        def get(self, *a, **k):
            self.calls += 1
            raise httpx.ConnectError("UNEXPECTED_EOF_WHILE_READING")

    http = DeadHttp()
    p = MusicBrainzProvider("Test/1.0 (x@y.z)", http=http)
    p._MIN_INTERVAL = 0  # niente throttle nel test

    assert p.lookup(title="A", artist="B") is None
    calls_before = http.calls
    assert calls_before > 0
    assert p.lookup(title="C", artist="D") is None  # se non gia' sospeso, riprova
    frozen = http.calls
    assert p.lookup(title="E", artist="F") is None  # sospeso: zero chiamate HTTP
    assert http.calls == frozen


def test_lookup_title_senza_artista_incorporato(db):
    # Tag sporchi dai download: titolo "Artist - Title". La query ai provider va
    # fatta col titolo nudo (GetSongBPM risponde 400, Last.fm non trova), senza
    # toccare il titolo salvato.
    from app.models import Track
    from app.services.feature_enrichment import enrich_features

    class Capture:
        name = "cap"

        def __init__(self):
            self.titles = []

        def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
            self.titles.append(title)
            return None

    t = Track(source_type="local_files", title="SLV - Dreamscapes", artist="SLV")
    db.add(t)
    db.commit()
    prov = Capture()
    enrich_features(db, prov, force=True, track_ids=[t.id])
    assert prov.titles == ["Dreamscapes"]
    db.refresh(t)
    assert t.title == "SLV - Dreamscapes"  # il titolo salvato resta intatto
