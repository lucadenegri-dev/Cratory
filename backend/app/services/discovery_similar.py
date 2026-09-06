"""Discovery "Simili": i parenti di un disco che possiedi.

Stesso mestiere del dig — lead non posseduti, ordinati per gusto — ma il seme non è
un genere astratto: è una traccia della libreria. Al posto della coppia probe/fetch
c'è una coppia risolvi/espandi: la sorgente riconosce la release d'origine, poi
percorre gli archi (stesso artista, stessa etichetta, stesso stile nel periodo) e
restituisce i record grezzi etichettati con l'arco che li ha raggiunti.

Deduplica, profilo di gusto e punteggio sono quelli del dig: qui non si reinventa
niente, si cambia solo da dove arrivano i candidati.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.services.dig_sources import DiscoveryLead, Reason
from app.services.discovery_dig import (
    TasteProfile,
    _dedup_key,
    _is_owned,
    _library_tracks,
    _owned_index,
    _score,
    _select,
    _weights,
)

logger = logging.getLogger(__name__)

# La semi-ampiezza della finestra temporale dell'arco stile, in anni.
PERIOD_YEARS = 3

# Gli archi, nell'ordine in cui si mostrano. Sono anche i `Reason.code` sui lead.
EDGES = ("same_artist", "same_label", "same_period_style")


@dataclass
class Origin:
    """Cosa la sorgente ha riconosciuto della traccia di partenza."""

    artist: str
    band_id: int
    title: str | None
    tralbum_id: int | None
    tralbum_type: str | None
    label: str | None
    label_id: int | None
    tag: str | None
    year: int | None
    source_url: str | None
    resolution: str  # "release" | "artist_only"
    # La discografia già scaricata da `resolve`: `expand` non la ricompra.
    discography: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class EdgeReport:
    """Quanti lead ha prodotto un arco, o perché non esiste.

    `count` e `absent_reason` si escludono: un arco percorso ha un conteggio (anche
    zero, se tutto era già posseduto), un arco assente ha un motivo. Confonderli
    farebbe dire alla UI "0 dischi" dove la verità è "non ho potuto guardare".
    """

    count: int | None = None
    absent_reason: str | None = None


@dataclass
class SimilarResult:
    origin: Origin | None
    leads: list[DiscoveryLead] = field(default_factory=list)
    edges: dict[str, EdgeReport] = field(default_factory=dict)


class SimilarSource(Protocol):
    """Una sorgente capace di riconoscere un disco e percorrerne le parentele."""

    name: str

    def resolve(self, track: Any) -> Origin | None: ...

    def expand(self, origin: Origin, *, style_period: bool) -> list[tuple[str, Any]]: ...

    def to_lead(self, edge: str, raw: Any) -> DiscoveryLead | None: ...


def similar(
    db: Session,
    track: Any,
    *,
    source: SimilarSource,
    style_period: bool = False,
    library: list | None = None,
) -> SimilarResult:
    """I lead non posseduti imparentati con `track`, ordinati per gusto."""
    if library is None:
        library = _library_tracks(db)

    origin = source.resolve(track)
    if origin is None:
        return SimilarResult(
            origin=None,
            edges={e: EdgeReport(absent_reason="no_band") for e in EDGES},
        )

    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library)

    raw_edges = source.expand(origin, style_period=style_period)

    # Un lead può essere raggiunto da più archi: si tiene una volta sola, con un
    # reason per ogni arco che l'ha raggiunto. La chiave è quella del dig, così
    # "(Original Mix)" e le ristampe collassano come là.
    by_key: dict[tuple[str, str], DiscoveryLead] = {}
    edge_hits: dict[str, int] = {e: 0 for e in EDGES}
    reached: dict[tuple[str, str], list[str]] = {}

    for edge, raw in raw_edges:
        lead = source.to_lead(edge, raw)
        if lead is None:
            continue
        key = _dedup_key(lead.artist_keys[0], lead.title)
        if _is_owned(lead, owned_tracks, owned_albums):
            continue
        if key not in by_key:
            by_key[key] = lead
            edge_hits[edge] += 1
            reached[key] = [edge]
        elif edge not in reached[key]:
            edge_hits[edge] += 1
            reached[key].append(edge)

    weights = _weights("genre", has_styles=False)
    leads: list[DiscoveryLead] = []
    for key, lead in by_key.items():
        lead.score = _score(lead, profile, weights, [])
        lead.reasons = [_edge_reason(edge, origin) for edge in reached[key]]
        leads.append(lead)

    selected = _select(leads)

    edges = {e: EdgeReport(count=edge_hits[e]) for e in EDGES}
    for edge, reason in _absent_edges(origin, style_period).items():
        edges[edge] = EdgeReport(absent_reason=reason)

    logger.info("Discovery similar %s track=%r: %s lead (archi %s)",
                source.name, origin.artist, len(selected), edges)
    return SimilarResult(origin=origin, leads=selected, edges=edges)


def _edge_reason(edge: str, origin: Origin) -> Reason:
    if edge == "same_label":
        return Reason(code=edge, data={"label": origin.label or ""})
    if edge == "same_period_style":
        year = origin.year or 0
        return Reason(code=edge, data={
            "tag": origin.tag or "",
            "year_from": year - PERIOD_YEARS,
            "year_to": year + PERIOD_YEARS,
        })
    return Reason(code=edge, data={})


def _absent_edges(origin: Origin, style_period: bool) -> dict[str, str]:
    """Quali archi NON sono stati percorsi, e perché.

    Deciso qui e non nella sorgente: è la stessa logica per qualsiasi sorgente, e
    tenerla accanto a `EDGES` impedisce che un arco nuovo resti senza motivo.

    La condizione deve rispecchiare ESATTAMENTE quando la sorgente riesce a
    percorrere l'arco, non solo quando i dati sono del tutto assenti: una release
    con un nome di etichetta ma senza `label_id`, o con `label_id` uguale alla band,
    non è percorribile, e riportarla come "0 dischi" direbbe che si è guardato.
    """
    absent: dict[str, str] = {}
    if origin.resolution == "release":
        # Percorribile solo con un `label_id` di una band DIVERSA dall'artista.
        if not origin.label_id or origin.label_id == origin.band_id:
            absent["same_label"] = "self_released"
    elif not origin.label:
        # `artist_only`: si passa dal nome nei tag del file, se c'è.
        absent["same_label"] = "no_label"
    if not style_period:
        absent["same_period_style"] = "off"
    elif not origin.tag:
        absent["same_period_style"] = "no_tag"
    elif origin.year is None:
        absent["same_period_style"] = "no_year"
    return absent
