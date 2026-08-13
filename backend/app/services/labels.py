"""Sezione Etichette (deterministica).

- ``album_label`` / ``_label_from_copyrights`` / ``_clean_label``: risolvono e
  normalizzano il nome di un'etichetta dall'album Spotify (usate dal Discovery per
  annotare i candidati). Metadata editoriale, non una feature di mixing.
- ``labels_overview``: aggrega la libreria per etichetta (conteggi + info derivate),
  normalizzando a read-time le varianti dello stesso label via ``_clean_label``.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.spotify import SpotifyError
from app.models import Track
from app.repositories import _EFFECTIVE_TAGS, _join_primary_file

_MAX_GENRES_PER_LABEL = 6

# "X under exclusive licence to Y" -> tiene solo Y (l'etichetta del master).
_LICENCE_RE = re.compile(r".*\bunder exclusive licen[cs]e to\s+", re.IGNORECASE)
# Suffissi societari finali da rimuovere ("Warp Records Limited" -> "Warp Records").
_LEGAL_SUFFIX_RE = re.compile(
    r"[\s,]+(?:Limited|Ltd\.?|LLC|Inc\.?|GmbH|B\.?V\.?|S\.?r\.?l\.?|S\.?A\.?|Pty\.?\s*Ltd\.?|Co\.?)\s*$",
    re.IGNORECASE,
)


def _clean_label(raw: str | None) -> str | None:
    """Normalizza il nome etichetta da un copyright verboso.

    - "X under exclusive licence to Y" -> Y (l'etichetta del master).
    - rimuove i suffissi societari finali (Limited/Ltd/LLC/Inc/GmbH/...).
    Idempotente: un nome gia' pulito resta invariato.
    """
    if not raw:
        return None
    s = raw.strip()
    s = _LICENCE_RE.sub("", s)          # tieni solo cio' dopo "under ... licence to"
    prev = None
    while prev != s:                    # strip ripetuto (es. "Records Limited Ltd")
        prev = s
        s = _LEGAL_SUFFIX_RE.sub("", s).strip()
    return s or None


def _label_from_copyrights(copyrights) -> str | None:
    """Ricava il nome dell'etichetta dai ``copyrights`` dell'album.

    Da novembre 2024 Spotify non espone piu' il campo ``label`` su
    GET /albums/{id} per le app in development mode, ma resta ``copyrights``.
    Si preferisce il copyright fonografico (tipo ``"P"``), che nomina l'owner del
    master / l'etichetta; si rimuovono simboli (©/℗/(C)/(P)) e l'anno iniziale.
    """
    if not copyrights:
        return None
    phono = corp = other = None
    for entry in copyrights:
        text = (entry or {}).get("text")
        if not text:
            continue
        typ = (entry or {}).get("type")
        if typ == "P" and phono is None:
            phono = text
        elif typ == "C" and corp is None:
            corp = text
        elif other is None:
            other = text
    text = phono or corp or other
    if not text:
        return None
    s = re.sub(r"^[\s©℗]+", "", text.strip())
    s = re.sub(r"^\(\s*[cp]\s*\)\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*\d{4}\s+", "", s).strip()
    return _clean_label(s)


def album_label(client, album_id: str) -> str | None:
    """Etichetta (pulita) di un album Spotify. Ritorna None se non risolvibile.

    Usata dal Discovery per annotare i candidati (che gia' deduplica per album nel
    proprio run). Nessuna cache persistente dopo lo slim-down dello schema:
    l'etichetta si rilegge dalla rete quando serve.
    """
    if not album_id:
        return None
    try:
        obj = client.get_album(album_id)
    except SpotifyError:
        return None
    label = None
    if obj:
        label = obj.get("label") or _label_from_copyrights(obj.get("copyrights"))
    return _clean_label(label)


def labels_overview(db: Session) -> list[dict]:
    """Aggrega la libreria per etichetta EFFETTIVA (tag del primary file quando la
    traccia ne ha uno, altrimenti streaming). Ritorna una lista ordinata per
    conteggio desc.

    Il drill-down dalla pagina etichette chiama GET /api/tracks?label=<label>,
    che filtra sullo stesso valore effettivo (_apply_track_filters,
    _EFFECTIVE_TAGS["label"]): aggregare qui sulla sola colonna streaming
    (Track.label) produrrebbe conteggi diversi da quelli del drill-down, e le
    etichette scritte solo sul file (il nuovo modal di modifica scrive lì) non
    comparirebbero affatto (F1).

    Ogni voce: label, track_count, artist_count, generi distinti (cap), range anni.
    """
    eff_label = _EFFECTIVE_TAGS["label"]
    eff_genre = _EFFECTIVE_TAGS["genre"]
    rows = db.execute(
        _join_primary_file(select(Track, eff_label, eff_genre))
        .where(eff_label.is_not(None), eff_label != "")
    ).all()

    # Merge a read-time delle varianti dello stesso label (es. "Warp Records
    # Limited" e "Warp Records Ltd" -> "Warp Records"): nessuna migrazione dati.
    buckets: dict[str, list[tuple[Track, str | None]]] = {}
    for t, label_val, genre_val in rows:
        key = _clean_label(label_val) or label_val
        buckets.setdefault(key, []).append((t, genre_val))

    out: list[dict] = []
    for label, items in buckets.items():
        artists = {t.artist for t, _ in items if t.artist}
        genres = {g for _, g in items if g}
        years = [t.year for t, _ in items if t.year]
        out.append({
            "label": label,
            "track_count": len(items),
            "artist_count": len(artists),
            "artists": sorted(artists),
            "genres": sorted(genres)[:_MAX_GENRES_PER_LABEL],
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
        })

    out.sort(key=lambda o: (-o["track_count"], o["label"].lower()))
    return out
