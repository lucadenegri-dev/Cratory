"""Estrazione AI di artist/title dai nomi file (Claude Haiku). Import lazy: il
modulo si carica senza il pacchetto `anthropic`; solo suggest() lo richiede.
Mockabile nei test (monkeypatch su ai_tags.suggest)."""

import os

from pydantic import BaseModel

_MODEL = "claude-haiku-4-5"
_CHUNK = 80
_PROMPT = (
    "Sei un assistente che estrae ARTISTA e TITOLO dai nomi di file di tracce "
    "musicali. Il formato tipico è 'Artista - Titolo'. Gestisci prefissi di "
    "numero traccia (es. '01 - ', '1. '), separatori multipli, e suffissi come "
    "'(Original Mix)'. Per ogni nome file numerato qui sotto restituisci un "
    "elemento con artist e title; mantieni lo STESSO ordine, un elemento per "
    "nome file. Se non riesci a determinare un campo con ragionevole certezza, "
    "mettilo a null. Non inventare."
)


class _Guess(BaseModel):
    artist: str | None = None
    title: str | None = None


class _Guesses(BaseModel):
    items: list[_Guess]


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def suggest(filenames: list[str]) -> list[dict]:
    """Ritorna [{'artist': str|None, 'title': str|None}] allineato a `filenames`."""
    if not filenames:
        return []
    from anthropic import Anthropic  # import lazy

    client = Anthropic()
    out: list[dict] = []
    for i in range(0, len(filenames), _CHUNK):
        chunk = filenames[i:i + _CHUNK]
        listing = "\n".join(f"{j}. {name}" for j, name in enumerate(chunk))
        resp = client.messages.parse(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": f"{_PROMPT}\n\n{listing}"}],
            output_format=_Guesses,
        )
        items = resp.parsed_output.items if resp.parsed_output else []
        for k in range(len(chunk)):
            g = items[k] if k < len(items) else _Guess()
            out.append({"artist": g.artist or None, "title": g.title or None})
    return out


_GENRE_PROMPT = (
    "Sei un assistente che assegna il GENERE musicale a tracce da DJ "
    "(prevalentemente musica elettronica). Per ogni traccia numerata qui sotto "
    "(formato 'Artista - Titolo') restituisci il genere principale più probabile, "
    "UNO solo (non una lista), normalizzato con casing canonico (es. 'Tech House', "
    "'Acid Techno', 'Drum & Bass'). Mantieni lo STESSO ordine, un elemento per "
    "traccia. Se non sei ragionevolmente sicuro mettilo a null; non inventare "
    "valori spazzatura (niente URL, niente 'Unbekannt', niente 'Music')."
)


class _GenreGuess(BaseModel):
    genre: str | None = None


class _GenreGuesses(BaseModel):
    items: list[_GenreGuess]


def suggest_genres(descriptions: list[str]) -> list[str | None]:
    """Ritorna un genere (o None) per ciascuna descrizione, allineato per indice."""
    if not descriptions:
        return []
    from anthropic import Anthropic  # import lazy

    client = Anthropic()
    out: list[str | None] = []
    for i in range(0, len(descriptions), _CHUNK):
        chunk = descriptions[i:i + _CHUNK]
        listing = "\n".join(f"{j}. {d}" for j, d in enumerate(chunk))
        resp = client.messages.parse(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": f"{_GENRE_PROMPT}\n\n{listing}"}],
            output_format=_GenreGuesses,
        )
        items = resp.parsed_output.items if resp.parsed_output else []
        for k in range(len(chunk)):
            g = items[k] if k < len(items) else _GenreGuess()
            out.append(g.genre or None)
    return out


_REVIEW_PROMPT = (
    "Sei un esperto di musica da DJ (prevalentemente elettronica) che verifica "
    "il GENERE di tracce. Per ogni traccia numerata qui sotto scegli il genere "
    "primario più accurato e specifico, UNO solo, con casing canonico (es. "
    "'Tech House', 'Acid Techno', 'Drum & Bass'). I candidati dei provider "
    "(MusicBrainz/Discogs) sono evidenza forte: preferiscili quando plausibili. "
    "Usa la ricerca web SOLO quando l'evidenza disponibile non basta a decidere. "
    "Mantieni lo STESSO ordine, un elemento per traccia. Imposta "
    "confidence='high' se sei sicuro, 'low' se incerto. Se non riesci a "
    "determinare il genere metti genre a null; non inventare valori spazzatura."
)


class _Review(BaseModel):
    genre: str | None = None
    confidence: str = "low"


class _Reviews(BaseModel):
    items: list[_Review]


def review_genres(items: list[dict]) -> list[dict]:
    """Rivede il genere di un batch di tracce con contesto provider e web search.
    items: [{'artist','title','album','label','current_genre','candidates'}];
    ritorna [{'genre': str|None, 'confidence': 'high'|'low'}] allineato per indice."""
    if not items:
        return []
    from anthropic import Anthropic  # import lazy

    client = Anthropic()
    lines = []
    for j, it in enumerate(items):
        parts = [f"{it.get('artist') or '?'} - {it.get('title') or '?'}"]
        if it.get("album"):
            parts.append(f"album: {it['album']}")
        if it.get("label"):
            parts.append(f"label: {it['label']}")
        if it.get("current_genre"):
            parts.append(f"genere attuale: {it['current_genre']}")
        if it.get("candidates"):
            parts.append("candidati provider: " + "; ".join(it["candidates"]))
        lines.append(f"{j}. " + " | ".join(parts))
    resp = client.messages.parse(
        model=_MODEL,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": 3}],
        messages=[{"role": "user",
                   "content": f"{_REVIEW_PROMPT}\n\n" + "\n".join(lines)}],
        output_format=_Reviews,
    )
    parsed = resp.parsed_output.items if resp.parsed_output else []
    out: list[dict] = []
    for k in range(len(items)):
        r = parsed[k] if k < len(parsed) else _Review()
        conf = "high" if r.confidence == "high" else "low"
        out.append({"genre": r.genre or None, "confidence": conf})
    return out
