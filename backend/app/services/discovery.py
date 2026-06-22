"""Discovery mode: scoperta di musica nuova compatibile.

Entry point attivo:
- EXPAND playlist: espande una playlist importata con tracce affini.

La vecchia modalita' gap-driven e' stata rimossa da API/UI/prodotto: la Gap Analysis
resta una lettura separata delle mancanze della playlist, non una sorgente di
suggerimenti Discovery.

Pipeline DETERMINISTICA (nessuna AI nei fatti):
1. Seed: artisti/tracce rappresentativi della playlist (o dell'intera libreria).
2. Similarita': Last.fm (artist.getsimilar / track.getsimilar / tag.gettoptracks).
3. Dedup: scarta cio' che e' gia' in libreria e i duplicati tra candidati.
4. Resolve: Spotify /search trasforma "artista + titolo" in traccia reale (id, cover, ISRC).
5. Rank: compatibilita' deterministica (match Last.fm), tracce risolvibili in testa.

L'AI (opzionale, a valle) si limita a SPIEGARE perche' ogni traccia e' coerente:
non sceglie i candidati e non inventa dati fattuali.

Tutte le dipendenze esterne sono iniettate (similarity client, resolver, llm) -> testabile senza rete.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Track
from app.services.labels import _clean_label

logger = logging.getLogger(__name__)

# Resolver: (artista, titolo) -> dict traccia Spotify, oppure None se non risolvibile.
Resolver = Callable[[str, str], dict[str, Any] | None]

# Tetti per contenere il numero di chiamate di rete e la latenza.
MAX_SEED_ARTISTS = 8
MAX_SEED_TRACKS = 5
SIMILAR_PER_ARTIST = 6
TOP_TRACKS_PER_ARTIST = 2
DEFAULT_LIMIT = 20
# Quanti candidati (oltre il limite) provare a risolvere su Spotify: tiene basso il
# numero di /search anche quando la similarita' restituisce centinaia di candidati.
RESOLVE_BUFFER = 10


class SimilaritySource(Protocol):
    def similar_artists(self, artist: str, *, limit: int = 20) -> list[dict[str, Any]]: ...
    def similar_tracks(self, artist: str, title: str, *, limit: int = 20) -> list[dict[str, Any]]: ...
    def artist_top_tracks(self, artist: str, *, limit: int = 10) -> list[dict[str, Any]]: ...
    def top_tracks_by_tag(self, tag: str, *, limit: int = 20) -> list[dict[str, Any]]: ...


class LLMExplainer(Protocol):
    def complete_json(
        self, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass
class DiscoveryCandidate:
    artist: str
    title: str
    match: float                       # similarita' Last.fm 0-1 (0 per il radar etichette)
    source: str                        # similar_artist | similar_track | tag | label
    seed: str | None = None            # cosa nella playlist (o quale etichetta) l'ha generata
    spotify_id: str | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    album_id: str | None = None        # per annotare l'etichetta dell'album
    isrc: str | None = None
    duration_seconds: int | None = None
    label: str | None = None           # etichetta (pulita), se nota
    label_owned: bool = False          # e' un'etichetta che gia' collezioni?
    score: float = 0.0                 # ordinamento interno di gusto (NON una compatibilita' tecnica)
    explanation: str | None = None     # narrativa AI (opzionale)

    @property
    def resolved(self) -> bool:
        return self.spotify_id is not None


@dataclass
class DiscoveryResult:
    mode: str                          # expand | labels
    scope: str                         # nome playlist o etichette
    seed_count: int
    candidates: list[DiscoveryCandidate] = field(default_factory=list)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _key(artist: str, title: str) -> tuple[str, str]:
    return _norm(artist), _norm(title)


EXPLAIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
            },
        }
    },
    "required": ["explanations"],
}

EXPAND_SYSTEM = """Sei un DJ esperto che aiuta a scoprire musica nuova.
Ricevi il profilo di una playlist e una lista di tracce CANDIDATE (suggerite da una
fonte di similarita'). Per ogni candidato spiega in UNA frase breve (max ~20 parole)
perche' si integra con la playlist: affinita' con gli artisti seed, coerenza di genere/mood,
ruolo che potrebbe avere nel set. Non inventare BPM o tonalita' (non li hai).
Rispondi solo nel formato JSON richiesto, una voce per ogni `index` ricevuto."""

def _library_tracks(db: Session) -> list[Track]:
    return list(db.scalars(select(Track)).all())


def _playlist_profile(tracks: list[Track]) -> dict:
    bpms = [t.bpm for t in tracks if t.bpm is not None]
    genres = [t.genre for t in tracks if t.genre]
    moods = [t.mood for t in tracks if t.mood]
    energies = [t.energy for t in tracks if t.energy is not None]
    return {
        "track_count": len(tracks),
        "top_artists": [a for a, _ in Counter(t.artist for t in tracks if t.artist).most_common(5)],
        "top_genres": [g for g, _ in Counter(genres).most_common(5)],
        "top_moods": [m for m, _ in Counter(moods).most_common(3)],
        "bpm_range": {"min": round(min(bpms), 1), "max": round(max(bpms), 1)} if bpms else {},
        "avg_energy": round(sum(energies) / len(energies)) if energies else None,
    }


def _seeds(tracks: list[Track]) -> tuple[list[str], list[tuple[str, str]]]:
    """Artisti seed (per frequenza) + alcune tracce seed rappresentative."""
    artist_freq = Counter(t.artist for t in tracks if t.artist)
    seed_artists = [a for a, _ in artist_freq.most_common(MAX_SEED_ARTISTS)]
    seed_tracks: list[tuple[str, str]] = []
    for t in tracks:
        if t.artist and t.title:
            seed_tracks.append((t.artist, t.title))
        if len(seed_tracks) >= MAX_SEED_TRACKS:
            break
    return seed_artists, seed_tracks


def _collect(
    similarity: SimilaritySource,
    seed_artists: list[str],
    seed_tracks: list[tuple[str, str]],
    tags: list[str],
) -> dict[tuple[str, str], DiscoveryCandidate]:
    """Interroga la fonte di similarita' e aggrega i candidati (max match per chiave)."""
    found: dict[tuple[str, str], DiscoveryCandidate] = {}

    def add(artist: str, title: str, match: float, source: str, seed: str) -> None:
        k = _key(artist, title)
        cur = found.get(k)
        if cur is None or match > cur.match:
            found[k] = DiscoveryCandidate(
                artist=artist, title=title, match=match, source=source, seed=seed,
            )

    # Tracce simili a tracce seed: il segnale piu' specifico.
    for artist, title in seed_tracks:
        for st in similarity.similar_tracks(artist, title):
            add(st["artist"], st["title"], st.get("match", 0.0), "similar_track", f"{artist} - {title}")

    # Artisti simili -> top tracks di ciascuno (concretizza l'artista in tracce).
    for seed in seed_artists:
        for sa in similarity.similar_artists(seed, limit=SIMILAR_PER_ARTIST):
            name, match = sa["name"], sa.get("match", 0.0)
            for tt in similarity.artist_top_tracks(name, limit=TOP_TRACKS_PER_ARTIST):
                add(tt["artist"], tt["title"], match, "similar_artist", seed)

    # Helper tag/genere mantenuto nel protocollo per eventuali usi futuri.
    for tag in tags:
        for tt in similarity.top_tracks_by_tag(tag):
            add(tt["artist"], tt["title"], 0.5, "tag", tag)

    return found


def _drop_in_library(
    candidates: dict[tuple[str, str], DiscoveryCandidate], library: list[Track]
) -> list[DiscoveryCandidate]:
    owned = {_key(t.artist or "", t.title or "") for t in library if t.artist and t.title}
    return [c for k, c in candidates.items() if k not in owned]


def _resolve_all(
    candidates: list[DiscoveryCandidate], resolve: Resolver | None, library_isrcs: set[str]
) -> list[DiscoveryCandidate]:
    """Risolve i candidati su Spotify e scarta quelli che (per ISRC) sono gia' in libreria."""
    if resolve is None:
        return candidates
    out: list[DiscoveryCandidate] = []
    for c in candidates:
        item = resolve(c.artist, c.title)
        if item:
            isrc = (item.get("external_ids") or {}).get("isrc")
            if isrc and isrc in library_isrcs:
                continue  # gia' in libreria con altro nome: scarta
            album = item.get("album") or {}
            images = album.get("images") or []
            c.spotify_id = item.get("id")
            c.spotify_url = (item.get("external_urls") or {}).get("spotify")
            c.album_art_url = images[0]["url"] if images else None
            c.album_id = album.get("id")
            c.isrc = isrc
            c.duration_seconds = round(item["duration_ms"] / 1000) if item.get("duration_ms") else None
        out.append(c)
    return out


def _rank(candidates: list[DiscoveryCandidate], limit: int) -> list[DiscoveryCandidate]:
    for c in candidates:
        c.score = max(0.0, min(1.0, c.match))
    # Prima le tracce risolvibili (azionabili), poi per affinita' di gusto (match Last.fm).
    candidates.sort(key=lambda c: (c.resolved, c.score, c.match), reverse=True)
    return candidates[:limit]


def _finalize(
    fresh: list[DiscoveryCandidate],
    resolve: Resolver | None,
    library_isrcs: set[str],
    limit: int,
) -> list[DiscoveryCandidate]:
    """Pre-ordina per match, risolve solo i migliori (budget limitato) e ri-ordina.

    Evita di interrogare Spotify per ogni candidato: la similarita' puo' produrne
    centinaia, ma ne servono `limit`. Si risolvono solo i `limit + RESOLVE_BUFFER`
    candidati col match piu' alto, poi le tracce risolvibili passano in testa.
    """
    fresh.sort(key=lambda c: c.match, reverse=True)
    if resolve is None:
        return _rank(fresh[:limit], limit)
    budget = fresh[: limit + RESOLVE_BUFFER]
    resolved = _resolve_all(budget, resolve, library_isrcs)
    return _rank(resolved, limit)


def _explain(
    llm: LLMExplainer,
    system: str,
    profile: dict,
    candidates: list[DiscoveryCandidate],
) -> None:
    payload: dict[str, Any] = {
        "playlist_profile": profile,
        "candidates": [
            {"index": i, "artist": c.artist, "title": c.title, "source": c.source, "match": c.match}
            for i, c in enumerate(candidates)
        ],
    }
    try:
        raw = llm.complete_json(system, payload, EXPLAIN_SCHEMA)
    except Exception as exc:  # noqa: BLE001 - la spiegazione AI e' best-effort, non deve far fallire il discovery
        logger.warning("Discovery: spiegazioni AI non disponibili: %s", exc)
        return
    for entry in raw.get("explanations") or []:
        idx = entry.get("index")
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            candidates[idx].explanation = entry.get("text") or None


# --- segnale-etichetta sulla similarita' (Part 3.3) --------------------------

AlbumLabelFn = Callable[[str], str | None]


def _annotate_labels(
    candidates: list[DiscoveryCandidate],
    album_label_fn: AlbumLabelFn,
    owned_labels: set[str],
) -> None:
    """Annota i candidati risolti con l'etichetta del loro album (e se la collezioni gia')."""
    cache: dict[str, str | None] = {}
    for c in candidates:
        if not c.album_id:
            continue
        if c.album_id not in cache:
            cache[c.album_id] = album_label_fn(c.album_id)  # gia' pulito
        lbl = cache[c.album_id]
        if lbl:
            c.label = lbl
            c.label_owned = lbl.lower() in owned_labels


# --- Radar Etichette (nuova sorgente) ----------------------------------------


def _release_year(item: dict[str, Any]) -> int | None:
    rd = (item.get("album") or {}).get("release_date")
    m = re.match(r"\s*(\d{4})", str(rd or ""))
    return int(m.group(1)) if m else None


def _recency_bonus(year: int | None) -> float:
    """Bonus 0..0.2: piu' recente -> piu' alto (lineare sugli ultimi 10 anni)."""
    if year is None:
        return 0.0
    span = 10
    current = datetime.now(timezone.utc).year
    frac = (year - (current - span)) / span
    return max(0.0, min(0.2, frac * 0.2))


def _label_candidate(item: dict[str, Any], label: str) -> DiscoveryCandidate | None:
    artists = item.get("artists") or []
    artist = artists[0].get("name") if artists else None
    title = item.get("name")
    if not artist or not title:
        return None
    album = item.get("album") or {}
    images = album.get("images") or []
    return DiscoveryCandidate(
        artist=artist, title=title, match=0.0, source="label", seed=label,
        spotify_id=item.get("id"),
        spotify_url=(item.get("external_urls") or {}).get("spotify"),
        album_art_url=images[0]["url"] if images else None,
        album_id=album.get("id"),
        isrc=(item.get("external_ids") or {}).get("isrc"),
        duration_seconds=round(item["duration_ms"] / 1000) if item.get("duration_ms") else None,
        label=label, label_owned=True,
    )


SearchByLabel = Callable[..., list[dict[str, Any]]]


def discover_by_labels(
    db: Session,
    *,
    labels: list[str],
    search_by_label: SearchByLabel,
    album_label_fn: AlbumLabelFn | None = None,  # non serve nel radar (la label e' il seed)
    library: list[Track] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> DiscoveryResult:
    """Tracce non possedute dalle etichette date, ordinate per affinita' di gusto.

    NON una compatibilita' tecnica: punteggio = quanto segui l'etichetta +
    sovrapposizione artisti gia' in libreria + recency. Interleave round-robin tra
    le etichette cosi' nessuna domina la lista.
    """
    if library is None:
        library = _library_tracks(db)
    owned_keys = {_key(t.artist or "", t.title or "") for t in library if t.artist and t.title}
    owned_isrcs = {t.isrc for t in library if t.isrc}
    owned_artists = {_norm(t.artist) for t in library if t.artist}
    label_counts: Counter[str] = Counter(
        (_clean_label(t.label) or t.label) for t in library if t.label
    )

    seen: set[tuple[str, str]] = set()
    per_label: list[list[DiscoveryCandidate]] = []
    for label in labels:
        affinity = min(label_counts.get(_clean_label(label) or label, 0), 10) / 10
        bucket: list[DiscoveryCandidate] = []
        for item in search_by_label(label, limit=limit) or []:
            cand = _label_candidate(item, label)
            if cand is None:
                continue
            k = _key(cand.artist, cand.title)
            if k in owned_keys or k in seen:
                continue
            if cand.isrc and cand.isrc in owned_isrcs:
                continue
            seen.add(k)
            overlap = 0.3 if _norm(cand.artist) in owned_artists else 0.0
            cand.score = affinity + overlap + _recency_bonus(_release_year(item))
            bucket.append(cand)
        bucket.sort(key=lambda c: c.score, reverse=True)
        per_label.append(bucket)

    # interleave round-robin tra le etichette, poi troncamento a limit
    interleaved: list[DiscoveryCandidate] = []
    for col in range(max((len(b) for b in per_label), default=0)):
        for bucket in per_label:
            if col < len(bucket):
                interleaved.append(bucket[col])
    candidates = interleaved[:limit]

    logger.info("Discovery radar etichette %s: %s candidati", labels, len(candidates))
    return DiscoveryResult(
        mode="labels", scope="; ".join(labels)[:60],
        seed_count=len(labels), candidates=candidates,
    )


def discover_for_playlist(
    db: Session,
    playlist_id: int,
    *,
    similarity: SimilaritySource,
    resolve: Resolver | None = None,
    llm: LLMExplainer | None = None,
    album_label_fn: AlbumLabelFn | None = None,
    owned_labels: set[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> DiscoveryResult:
    """Espande una playlist con tracce affini scoperte via similarita'."""
    from app.repositories import get_playlist, tracks_for_playlist

    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise ValueError("Playlist non trovata")
    tracks = tracks_for_playlist(db, playlist_id)
    seed_artists, seed_tracks = _seeds(tracks)

    found = _collect(similarity, seed_artists, seed_tracks, tags=[])
    library = _library_tracks(db)
    fresh = _drop_in_library(found, library)
    library_isrcs = {t.isrc for t in library if t.isrc}
    ranked = _finalize(fresh, resolve, library_isrcs, limit)

    # Segnale-etichetta: annota e fa salire leggermente cio' che e' su un'etichetta
    # che gia' collezioni (boost di gusto, non tecnico).
    if album_label_fn is not None and owned_labels is not None:
        _annotate_labels(ranked, album_label_fn, owned_labels)
        ranked.sort(key=lambda c: (c.resolved, c.label_owned, c.score), reverse=True)

    if llm and ranked:
        _explain(llm, EXPAND_SYSTEM, _playlist_profile(tracks), ranked)

    logger.info("Discovery expand playlist %s: %s candidati (da %s seed artisti)",
                playlist_id, len(ranked), len(seed_artists))
    return DiscoveryResult(
        mode="expand", scope=playlist.name,
        seed_count=len(seed_artists) + len(seed_tracks), candidates=ranked,
    )
