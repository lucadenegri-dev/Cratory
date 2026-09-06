"""Il motore dei simili: orchestrazione, archi, ranking. Nessuna rete."""

import pytest

from app.models import Track
from app.services.dig_sources import DiscoveryLead
from app.services.discovery_similar import (
    EdgeReport,
    Origin,
    SimilarResult,
    similar,
)


def _track(**kw) -> Track:
    """Una Track non persistita: il motore legge solo gli attributi."""
    base = dict(id=1, artist="Jasmín", title="Bite The Hand", album="Bite The Hand",
                label="Hessle Audio", genre="Bass", year=2025, has_local_file=True)
    base.update(kw)
    return Track(**base)


def _lead(artist="Pearson Sound", title="Which Way Is Up", **kw) -> DiscoveryLead:
    return DiscoveryLead(artist=artist, artist_keys=[artist.lower()], title=title,
                         source="bandcamp", **kw)


class _FakeSource:
    """Sorgente finta: restituisce origine e archi prefissati, registra le chiamate."""

    name = "bandcamp"

    def __init__(self, origin=None, edges=None):
        self._origin = origin
        self._edges = edges or []
        self.expand_calls: list[dict] = []

    def resolve(self, track):
        return self._origin

    def expand(self, origin, *, style_period):
        self.expand_calls.append({"style_period": style_period})
        return list(self._edges)

    def to_lead(self, edge, raw):
        return raw


def _origin(**kw) -> Origin:
    base = dict(artist="Jasmín", band_id=637178087, title="Bite The Hand",
                tralbum_id=4024735967, tralbum_type="a", label="Hessle Audio",
                label_id=2788766970, tag="bass", year=2025,
                source_url="https://x.bandcamp.com/album/y", resolution="release",
                discography=[])
    base.update(kw)
    return Origin(**base)


def test_artist_absent_from_bandcamp_gives_no_origin_and_no_leads(db):
    source = _FakeSource(origin=None)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.origin is None
    assert result.leads == []
    assert result.edges["same_artist"] == EdgeReport(count=None, absent_reason="no_band")
    assert result.edges["same_label"].absent_reason == "no_band"
    assert result.edges["same_period_style"].absent_reason == "no_band"
    # Nessuna espansione: senza band non c'è nulla da espandere.
    assert source.expand_calls == []


def test_leads_carry_one_reason_per_edge_that_reached_them(db):
    lead = _lead()
    source = _FakeSource(origin=_origin(), edges=[("same_artist", lead),
                                                  ("same_label", lead)])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 1
    codes = sorted(r.code for r in result.leads[0].reasons)
    assert codes == ["same_artist", "same_label"]


def test_edge_counts_report_leads_produced_after_dedup(db):
    # Artisti DIVERSI di proposito: con tre lead dello stesso artista il tetto
    # `_MAX_PER_ARTIST` (2) ne taglierebbe uno e il test misurerebbe il tetto
    # invece del conteggio degli archi. Il tetto ha il suo test, più sotto.
    source = _FakeSource(origin=_origin(), edges=[
        ("same_artist", _lead(artist="Artista A", title="A")),
        ("same_label", _lead(artist="Artista B", title="B")),
        ("same_label", _lead(artist="Artista C", title="C")),
    ])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_artist"].count == 1
    assert result.edges["same_label"].count == 2
    assert len(result.leads) == 3


def test_style_period_off_is_an_absent_edge_not_a_zero_count(db):
    source = _FakeSource(origin=_origin(), edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_period_style"] == EdgeReport(count=None, absent_reason="off")
    assert source.expand_calls == [{"style_period": False}]


def test_a_label_the_source_cannot_walk_is_absent_not_a_zero_count(db):
    # `label_id` uguale alla band: autoprodotto. L'arco non è percorribile, e dire
    # "0 dischi" affermerebbe di aver guardato.
    source = _FakeSource(origin=_origin(label_id=637178087, label="Jasmín"),
                         edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"] == EdgeReport(count=None,
                                                    absent_reason="self_released")


def test_a_missing_label_in_artist_only_is_absent_for_its_own_reason(db):
    source = _FakeSource(origin=_origin(resolution="artist_only", label=None,
                                        label_id=None, title=None, tralbum_id=None),
                         edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"].absent_reason == "no_label"


def test_one_artist_cannot_monopolise_the_grid(db):
    # La discografia dell'artista di partenza mangerebbe la griglia senza il tetto
    # che il dig applica già (_MAX_PER_ARTIST).
    edges = [("same_artist", _lead(title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 2
    # L'arco però ha davvero prodotto 5 lead: il tetto taglia la vista, non il conto.
    assert result.edges["same_artist"].count == 5


def test_owned_leads_are_dropped(db):
    owned = _track(id=2, artist="Pearson Sound", title="Which Way Is Up",
                   album="Which Way Is Up")
    source = _FakeSource(origin=_origin(), edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False,
                     library=[owned])
    assert result.leads == []
    assert result.edges["same_artist"].count == 0
