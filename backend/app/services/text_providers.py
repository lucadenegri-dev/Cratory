"""Catena provider testuali: MusicBrainz (identità/label/genere/anno) poi Discogs
(riempie label/genere mancanti). Ritorna solo i campi risolti, genere normalizzato.
I provider sono iniettabili → test senza rete; in produzione li costruisce il router."""

from dataclasses import dataclass, field
from typing import Any

from app.integrations.discogs_meta import DiscogsMetaClient
from app.integrations.musicbrainz import MusicBrainzProvider
from app.services.genre_norm import normalize_genre


def _year(value) -> int | None:
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


@dataclass
class ResolvedText:
    fields: dict[str, tuple[Any, str]] = field(default_factory=dict)
    release_mbids: list[str] = field(default_factory=list)
    confidence: str | None = None


def resolve(file, *, mb=None, discogs=None) -> ResolvedText:
    """Come lookup_with_conf, ma espone anche i release-MBID e la confidenza MB
    complessiva (per la ricerca cover). fields ha lo stesso contenuto di prima."""
    out: dict[str, tuple[Any, str]] = {}
    release_mbids: list[str] = []
    overall: str | None = None
    mb_res = mb.lookup(title=file.title, artist=file.artist,
                       isrc=(file.isrc.strip() or None) if file.isrc else None,
                       mbid=getattr(file, "mbid", None)) if mb else None
    if mb_res:
        conf = "high" if (mb_res.get("confidence") or 0) >= 95 else "text"
        overall = conf
        release_mbids = mb_res.get("release_mbids") or []
        if mb_res.get("canonical_artist"):
            out["artist"] = (mb_res["canonical_artist"], conf)
        if mb_res.get("canonical_title"):
            out["title"] = (mb_res["canonical_title"], conf)
        if mb_res.get("canonical_album"):
            out["album"] = (mb_res["canonical_album"], conf)
        if mb_res.get("label"):
            out["label"] = (mb_res["label"], conf)
        if mb_res.get("genre_primary") and (g := normalize_genre(mb_res["genre_primary"])) is not None:
            out["genre"] = (g, conf)
        if (y := _year(mb_res.get("release_date"))) is not None:
            out["year"] = (y, conf)

    # Discogs riempie SOLO i buchi (MusicBrainz ha precedenza) ed è sempre 'text'.
    needs = "label" not in out or "genre" not in out
    if discogs and needs:
        dg_res = discogs.lookup(artist=file.artist, title=file.title)
        if dg_res:
            if "label" not in out and dg_res.get("label"):
                out["label"] = (dg_res["label"], "text")
            if "genre" not in out and dg_res.get("genre_primary") \
                    and (g := normalize_genre(dg_res["genre_primary"])) is not None:
                out["genre"] = (g, "text")
            if "year" not in out and (y := _year(dg_res.get("release_date"))) is not None:
                out["year"] = (y, "text")
    return ResolvedText(fields=out, release_mbids=release_mbids, confidence=overall)


def lookup_with_conf(file, *, mb=None, discogs=None) -> dict[str, tuple[Any, str]]:
    """Come lookup() ma ogni campo porta la confidenza con cui è stato ottenuto:
    'high' = match MusicBrainz esatto (MBID/ISRC, confidence >= 95), 'text' =
    match testuale MusicBrainz o qualunque campo da Discogs (che cerca per testo)."""
    return resolve(file, mb=mb, discogs=discogs).fields


def lookup(file, *, mb=None, discogs=None) -> dict[str, Any]:
    """Compat: mappa campo→valore (senza confidenza). Delegata a lookup_with_conf."""
    return {k: v for k, (v, _c) in lookup_with_conf(file, mb=mb, discogs=discogs).items()}
