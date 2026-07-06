"""Catena provider testuali: MusicBrainz (identità/label/genere/anno) poi Discogs
(riempie label/genere mancanti). Ritorna solo i campi risolti, genere normalizzato.
I provider sono iniettabili → test senza rete; in produzione li costruisce il router."""

from typing import Any

from app.integrations.discogs_meta import DiscogsMetaClient
from app.integrations.musicbrainz import MusicBrainzProvider
from app.services.genre_norm import normalize_genre


def _year(value) -> int | None:
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


def lookup(file, *, mb=None, discogs=None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    mb_res = mb.lookup(title=file.title, artist=file.artist,
                       isrc=(file.isrc.strip() or None) if file.isrc else None,
                       mbid=getattr(file, "mbid", None)) if mb else None
    if mb_res:
        if mb_res.get("canonical_artist"):
            out["artist"] = mb_res["canonical_artist"]
        if mb_res.get("canonical_title"):
            out["title"] = mb_res["canonical_title"]
        if mb_res.get("canonical_album"):
            out["album"] = mb_res["canonical_album"]
        if mb_res.get("label"):
            out["label"] = mb_res["label"]
        if mb_res.get("genre_primary") and (g := normalize_genre(mb_res["genre_primary"])) is not None:
            out["genre"] = g
        if (y := _year(mb_res.get("release_date"))) is not None:
            out["year"] = y

    # Discogs riempie SOLO i buchi (MusicBrainz ha precedenza).
    needs = "label" not in out or "genre" not in out
    if discogs and needs:
        dg_res = discogs.lookup(artist=file.artist, title=file.title)
        if dg_res:
            if "label" not in out and dg_res.get("label"):
                out["label"] = dg_res["label"]
            if "genre" not in out and dg_res.get("genre_primary") \
                    and (g := normalize_genre(dg_res["genre_primary"])) is not None:
                out["genre"] = g
            if "year" not in out and (y := _year(dg_res.get("release_date"))) is not None:
                out["year"] = y
    return out
