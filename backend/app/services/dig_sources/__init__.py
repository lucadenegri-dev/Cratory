"""Il confine fra il motore del dig e le sorgenti che lo alimentano.

Il motore ragiona in ITEM — una finestra (offset, count) dentro la pila di un seme —
e ogni sorgente traduce quella finestra nella PROPRIA paginazione: numeri di pagina
per Discogs, sfogliata col cursore per Bandcamp. Senza questo confine il motore
dovrebbe conoscere la granularita' di ognuna, che e' esattamente cio' che rende
impossibile aggiungerne una terza.

`DiscoveryLead` e `Reason` vivono qui e non nel motore perche' sono la lingua franca
fra i due: se stessero in `discovery_dig`, ogni sorgente dovrebbe importare dal
modulo che la usa e l'import sarebbe circolare.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

# Quanti item scarica un dig. Sono le 3 pagine da 100 del vecchio motore Discogs,
# dette in un'unita' che vale per tutte le sorgenti.
WINDOW_ITEMS = 300


@dataclass(frozen=True)
class Seed:
    type: str      # "genre" | "label"
    value: str


@dataclass
class Pile:
    """Quanto e' alta la pila di un seme e quanto ne raggiunge la sorgente.

    `height` e' il conteggio dichiarato dal provider; `reach` e' il tetto oltre cui
    QUELLA sorgente non sa andare (pagina 101 su Discogs, il costo della sfogliata su
    Bandcamp). Tenerli separati e' l'unico modo per dire "ce ne sono 434.149, ne vedi
    3.000" invece di far credere che la pila sia corta.

    `handle` e' lo stato che `probe` ha gia' pagato e `fetch` non deve ricomprare: i
    filtri Discogs gia' risolti, il tag normalizzato, la discografia gia' scaricata.
    """
    height: int
    reach: int
    resolution: str | None = None
    handle: Any = None


@dataclass
class Reason:
    """Spiegazione strutturata: codice + payload dati. Il testo lo compone la UI."""
    code: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryLead:
    artist: str
    title: str
    year: int | None = None
    label: str | None = None
    styles: list[str] = field(default_factory=list)   # tutti gli style della release
    artist_keys: list[str] = field(default_factory=list)  # interno: match, non DTO
    source: str = "discogs"
    seed: str | None = None
    # Neutro per costruzione: due sorgenti non possono convivere in un campo che si
    # chiama `discogs_id`. E' una stringa perche' Bandcamp ci mette una coppia
    # "band_id:item_id" — il dettaglio release ha bisogno di entrambi.
    source_id: str | None = None
    source_url: str | None = None
    thumb_url: str | None = None
    # Stream diretto, quando la sorgente lo regala col risultato (Bandcamp). Se manca,
    # la preview si risolve come sempre (iTunes/YouTube).
    stream_url: str | None = None
    have: int = 0
    want: int = 0
    format_badge: str | None = None    # EP | LP | Album | Single | 12" | None
    isrc: str | None = None
    score: float = 0.0
    reasons: list[Reason] = field(default_factory=list)


class DigSource(Protocol):
    """Una pila da cui scavare.

    `probe` misura e risolve il seme (una sola volta: cio' che ha pagato lo lascia in
    `Pile.handle`). `fetch` restituisce i record grezzi della finestra chiesta.
    `to_lead` li mappa, ed e' l'unico posto che conosce la forma dei dati del provider.
    """
    name: str

    def probe(self, seed: Seed) -> Pile: ...

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[Any]: ...

    def to_lead(self, raw: Any, seed: Seed) -> DiscoveryLead | None: ...
