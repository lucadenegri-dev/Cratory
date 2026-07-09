"""Sezione Etichette: normalizzazione label (Discovery) + panoramica per etichetta."""

from app.models import Track
from app.services.labels import (
    _clean_label,
    _label_from_copyrights,
    album_label,
    labels_overview,
)


class _FakeSpotifyCopyrights:
    """Riproduce l'API Spotify 2024+ in development mode: GET /albums/{id} NON
    restituisce piu' il campo ``label``, solo ``copyrights``."""

    def __init__(self, track_albums=None, album_copyrights=None):
        self._track_albums = track_albums or {}
        self._album_copyrights = album_copyrights or {}
        self.track_calls = 0
        self.album_calls = 0

    def get_track_metadata(self, sid):
        self.track_calls += 1
        return {"id": sid, "album": {"id": self._track_albums.get(sid)}}

    def get_album(self, album_id):
        self.album_calls += 1
        return {"id": album_id, "copyrights": self._album_copyrights.get(album_id, [])}


def test_clean_label_strips_licence_to_and_legal_suffix():
    # "X under exclusive licence to Y" -> Y (l'etichetta del master)
    assert _clean_label(
        "Ridge Valley Digital under exclusive licence to Warp Records Limited"
    ) == "Warp Records"
    # variante ortografica "license"
    assert _clean_label("Foo under exclusive license to Hyperdub Ltd") == "Hyperdub"
    # suffissi societari finali rimossi
    assert _clean_label("XL Recordings Ltd") == "XL Recordings"
    assert _clean_label("Some Label LLC") == "Some Label"
    assert _clean_label("Kompakt GmbH") == "Kompakt"
    # idempotenza: un nome gia' pulito resta invariato
    assert _clean_label("Warp Records") == "Warp Records"
    # None / vuoto
    assert _clean_label(None) is None
    assert _clean_label("   ") is None


def test_clean_label_keeps_plain_names():
    # nessun match di suffisso/licenza: il nome resta com'e'
    assert _clean_label("Hyperdub") == "Hyperdub"
    assert _clean_label("AD 93") == "AD 93"


def test_album_label_returns_cleaned_label():
    client = _FakeSpotifyCopyrights(album_copyrights={"alb1": [
        {"text": "2013 Ridge Valley Digital under exclusive licence to Warp Records Limited", "type": "P"},
    ]})
    assert album_label(client, "alb1") == "Warp Records"
    assert client.album_calls == 1
    # album id assente -> None senza chiamate di rete
    assert album_label(client, "") is None
    assert client.album_calls == 1


def test_labels_overview_merges_label_variants(db):
    # tre tracce, due varianti che puliscono allo stesso "Warp Records"
    _track(db, spotify_id="s1", title="A", artist="Artist 1", year=2018,
           label="Warp Records Limited")
    _track(db, spotify_id="s2", title="B", artist="Artist 2", year=2020,
           label="Ridge Valley under exclusive licence to Warp Records Ltd")
    _track(db, spotify_id="s3", title="C", artist="Artist 3", year=2012, label="Hyperdub")

    overview = labels_overview(db)
    by_label = {o["label"]: o for o in overview}

    # le due varianti confluiscono in un unico bucket "Warp Records"
    assert "Warp Records" in by_label
    assert by_label["Warp Records"]["track_count"] == 2
    assert by_label["Warp Records"]["artist_count"] == 2
    assert by_label["Warp Records"]["year_min"] == 2018
    assert by_label["Warp Records"]["year_max"] == 2020
    assert by_label["Hyperdub"]["track_count"] == 1


def test_label_from_copyrights_strips_year_and_symbols():
    assert _label_from_copyrights([{"text": "2013 Warp Records", "type": "P"}]) == "Warp Records"
    # _clean_label rimuove anche il suffisso societario finale ("Ltd")
    assert _label_from_copyrights([{"text": "© 2020 XL Recordings Ltd", "type": "C"}]) == "XL Recordings"
    assert _label_from_copyrights([{"text": "(P) 2021 Hyperdub", "type": "P"}]) == "Hyperdub"
    assert _label_from_copyrights([]) is None
    assert _label_from_copyrights(None) is None
    # preferisce il copyright fonografico (P), che nomina l'etichetta del master
    assert _label_from_copyrights([
        {"text": "2019 Distributor Inc", "type": "C"},
        {"text": "2019 Real Label", "type": "P"},
    ]) == "Real Label"


def _track(db, **kw) -> Track:
    kw.setdefault("source_type", "spotify")
    t = Track(**kw)
    db.add(t)
    db.commit()
    return t


def test_labels_overview_aggregates_counts_and_info(db):
    _track(db, spotify_id="s1", title="A", artist="Artist 1", genre="idm", year=2018, label="Warp")
    _track(db, spotify_id="s2", title="B", artist="Artist 2", genre="electronic", year=2020, label="Warp")
    _track(db, spotify_id="s3", title="C", artist="Artist 3", genre="dubstep", year=2012, label="Hyperdub")
    _track(db, spotify_id="s4", title="D", artist="Artist 4")  # senza label -> esclusa

    overview = labels_overview(db)

    assert [o["label"] for o in overview] == ["Warp", "Hyperdub"]  # ordinate per conteggio desc
    warp = overview[0]
    assert warp["track_count"] == 2
    assert warp["artist_count"] == 2
    assert set(warp["artists"]) == {"Artist 1", "Artist 2"}
    assert set(warp["genres"]) == {"idm", "electronic"}
    assert warp["year_min"] == 2018
    assert warp["year_max"] == 2020
