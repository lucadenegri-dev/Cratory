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
