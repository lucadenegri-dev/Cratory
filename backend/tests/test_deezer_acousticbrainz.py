"""Test dei provider gratuiti aggiunti per migliorare la copertura dell'enrichment:
Deezer (ISRC->BPM) e AcousticBrainz (MBID->BPM/key/mood/danceability/voce), oltre al
passaggio del `context` (MBID) lungo la catena. Nessuna chiamata HTTP reale.
"""

import httpx
import pytest

from app.integrations.acousticbrainz import AcousticBrainzProvider
from app.integrations.deezer import DeezerProvider
from app.integrations.getsongbpm import ChainedFeatureProvider
from app.integrations.musicbrainz import MusicBrainzProvider


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


class _RoutedHttp:
    """Client finto che risponde in base a una sottostringa dell'URL."""

    def __init__(self, routes: dict[str, tuple]):
        # routes: {substring: (payload, status)}
        self.routes, self.calls = routes, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        for sub, (payload, status) in self.routes.items():
            if sub in url:
                return _FakeResp(payload, status)
        return _FakeResp({}, 404)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.integrations._http.time.sleep", lambda *_: None)


# --- Deezer ------------------------------------------------------------------


def test_deezer_parse_bpm_present():
    out = DeezerProvider._parse({"bpm": 114.84, "title": "X"})
    assert out["bpm"] == 114.8
    assert out["confidence"] == 90


def test_deezer_parse_bpm_zero_is_unknown():
    assert DeezerProvider._parse({"bpm": 0}) is None
    assert DeezerProvider._parse({"bpm": None}) is None
    assert DeezerProvider._parse({}) is None


def test_deezer_lookup_requires_isrc():
    p = DeezerProvider(http=_RoutedHttp({}))
    assert p.lookup(title="X", artist="Y") is None  # niente ISRC -> niente match


def test_deezer_lookup_by_isrc_no_network():
    http = _RoutedHttp({"/track/isrc:": ({"bpm": 128, "title": "Da Funk"}, 200)})
    p = DeezerProvider(http=http)
    out = p.lookup(title="Da Funk", artist="Daft Punk", isrc="GBDUW0000059")
    assert out["bpm"] == 128.0
    assert "isrc:GBDUW0000059" in http.calls[0][0]


def test_deezer_lookup_error_payload_returns_none():
    http = _RoutedHttp({"/track/isrc:": ({"error": {"code": 800, "message": "no data"}}, 200)})
    p = DeezerProvider(http=http)
    assert p.lookup(title="X", artist="Y", isrc="XX0000000000") is None


# --- AcousticBrainz: parsing -------------------------------------------------


def test_acousticbrainz_parse_low_level():
    low = {"rhythm": {"bpm": 128.347702026}, "tonal": {"key_key": "A", "key_scale": "minor"}}
    out = AcousticBrainzProvider._parse_low_level(low)
    assert out["bpm"] == 128.3
    assert out["camelot_key"] == "8A"  # Am


def test_acousticbrainz_parse_low_level_major_key():
    out = AcousticBrainzProvider._parse_low_level(
        {"rhythm": {"bpm": 120}, "tonal": {"key_key": "C", "key_scale": "major"}}
    )
    assert out["camelot_key"] == "8B"  # C maggiore


def test_acousticbrainz_parse_high_level():
    high = {"highlevel": {
        "danceability": {"all": {"danceable": 0.757, "not_danceable": 0.243}},
        "voice_instrumental": {"all": {"instrumental": 0.2, "voice": 0.8}},
        "mood_happy": {"all": {"happy": 0.05, "not_happy": 0.95}},
        "mood_relaxed": {"all": {"relaxed": 0.96, "not_relaxed": 0.04}},
        "mood_aggressive": {"all": {"aggressive": 0.01, "not_aggressive": 0.99}},
    }}
    out = AcousticBrainzProvider._parse_high_level(high)
    assert out["danceability"] == 76
    assert out["vocalness"] == 80
    assert out["mood"] == "chill"  # mood_relaxed dominante (0.96)


def test_acousticbrainz_dominant_mood_below_threshold_is_none():
    # nessun mood supera la soglia 0.6 -> nessun mood
    hl = {"mood_happy": {"all": {"happy": 0.4}}, "mood_relaxed": {"all": {"relaxed": 0.55}}}
    assert AcousticBrainzProvider._dominant_mood(hl) is None


def test_acousticbrainz_unwrap_shapes():
    direct = {"rhythm": {"bpm": 120}}
    assert AcousticBrainzProvider._unwrap(direct) is direct
    nested = {"mbid-1": {"0": {"highlevel": {"x": 1}}}}
    assert AcousticBrainzProvider._unwrap(nested) == {"highlevel": {"x": 1}}
    nested2 = {"mbid-1": {"tonal": {"key_key": "A"}}}
    assert AcousticBrainzProvider._unwrap(nested2) == {"tonal": {"key_key": "A"}}


# --- AcousticBrainz: lookup --------------------------------------------------


def test_acousticbrainz_lookup_requires_mbid():
    p = AcousticBrainzProvider(http=_RoutedHttp({}))
    assert p.lookup(title="X", artist="Y") is None            # nessun context
    assert p.lookup(title="X", artist="Y", context={}) is None  # context senza mbid


def test_acousticbrainz_lookup_merges_low_and_high():
    http = _RoutedHttp({
        "/low-level": ({"rhythm": {"bpm": 124}, "tonal": {"key_key": "G", "key_scale": "minor"}}, 200),
        "/high-level": ({"highlevel": {
            "danceability": {"all": {"danceable": 0.9}},
            "mood_aggressive": {"all": {"aggressive": 0.8}},
        }}, 200),
    })
    p = AcousticBrainzProvider(http=http)
    out = p.lookup(title="X", artist="Y", context={"mbid": "MBID-1"})
    assert out["bpm"] == 124.0
    assert out["camelot_key"] == "6A"   # Gm
    assert out["danceability"] == 90
    assert out["mood"] == "aggressive"
    assert out["confidence"] == 80


def test_acousticbrainz_lookup_404_returns_none():
    http = _RoutedHttp({"/low-level": ({}, 404), "/high-level": ({}, 404)})
    p = AcousticBrainzProvider(http=http)
    assert p.lookup(title="X", artist="Y", context={"mbid": "absent"}) is None


# --- MusicBrainz: cattura MBID -----------------------------------------------


def test_musicbrainz_parse_recording_captures_mbid():
    p = MusicBrainzProvider("ua")
    rec = {"id": "11111111-2222-3333-4444-555555555555", "title": "Track", "score": 90}
    out = p._parse_recording(rec, isrc=None, exact=False)
    assert out["mbid"] == "11111111-2222-3333-4444-555555555555"


# --- catena: il context (MBID) arriva ai provider successivi -----------------


class _MbStub:
    name = "musicbrainz"

    def lookup(self, **_):
        return {"mbid": "MBID-1", "genre_primary": "techno", "confidence": 90}


class _CtxReader:
    """Finge AcousticBrainz: produce dati solo se trova l'MBID nel context."""

    name = "acousticbrainz"

    def __init__(self):
        self.seen_mbid = "UNSET"

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
        self.seen_mbid = (context or {}).get("mbid")
        if self.seen_mbid == "MBID-1":
            return {"bpm": 128.0, "camelot_key": "8A", "confidence": 80}
        return None


def test_chain_passes_mbid_context_to_later_provider():
    reader = _CtxReader()
    out = ChainedFeatureProvider([_MbStub(), reader]).lookup(title="t", artist="a")
    assert reader.seen_mbid == "MBID-1"        # ha visto l'MBID del provider precedente
    assert out["bpm"] == 128.0
    assert out["camelot_key"] == "8A"
    assert out["genre_primary"] == "techno"    # completato da MusicBrainz
    assert out["confidence"] == 90             # massima tra i contributori
