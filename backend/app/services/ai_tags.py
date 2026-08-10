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


_REVIEW_PROMPT = (
    "Sei un esperto di musica da DJ (prevalentemente elettronica) che verifica "
    "il GENERE di tracce. Per ogni traccia numerata qui sotto scegli il genere "
    "primario più accurato e specifico, UNO solo, con casing canonico (es. "
    "'Tech House', 'Acid Techno', 'Drum & Bass'). I candidati dei provider "
    "(MusicBrainz/Discogs) sono evidenza forte: preferiscili quando plausibili. "
    "Usa la ricerca web SOLO quando l'evidenza disponibile non basta a decidere. "
    "IMPORTANTE: per ogni elemento della risposta valorizza SEMPRE index con il "
    "numero che precede la traccia (es. per la riga '3. ...' usa index=3) e "
    "title con il titolo esattamente come compare in quella riga dopo il "
    "trattino: servono a verificare che la risposta sia abbinata alla traccia "
    "giusta e non a quella vicina, quindi non ometterli e non riecheggiare il "
    "titolo di un'altra riga. Non serve rispondere nello stesso ordine delle "
    "tracce, ma ogni risposta deve riportare l'index e il title corretti della "
    "traccia a cui si riferisce. Imposta confidence='high' se sei sicuro, "
    "'low' se incerto. Se non riesci a determinare il genere metti genre a "
    "null; non inventare valori spazzatura."
)


class _Review(BaseModel):
    index: int = -1
    title: str | None = None
    genre: str | None = None
    confidence: str = "low"


class _Reviews(BaseModel):
    items: list[_Review]


def _normalize_title_for_match(title: str | None) -> str:
    """Forma normalizzata di un titolo per il confronto della guardia: solo
    caratteri alfanumerici in minuscolo, così maiuscole/minuscole, spazi,
    punteggiatura e apostrofi (dritti o tipografici, es. '’') non causano
    falsi scarti."""
    if title is None:
        return ""
    return "".join(ch.lower() for ch in title if ch.isalnum())


class AiReviewError(Exception):
    """Il batch non ha prodotto un output strutturato (parsing fallito, oppure
    il turno è stato consumato interamente dalla ricerca web senza arrivare a
    un `parsed_output`). Va distinto dal caso in cui l'AI risponde ma non sa
    decidere un singolo item (quello resta un `genre: None` legittimo): qui
    non abbiamo ricevuto alcuna risposta valida, quindi il chiamante
    (genre_review.review) deve trattare l'intero batch come fallito invece di
    marcare i file come revisionati."""


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
    if resp.parsed_output is None:
        # Nessun output strutturato per l'intero batch (parsing fallito o
        # turno esaurito in ricerca web): diverso da una risposta valida ma
        # più corta, che viene invece completata item per item più sotto.
        raise AiReviewError(
            "review_genres: nessun output strutturato ricevuto dal modello "
            "(parsing fallito o turno consumato dalla ricerca web)")
    parsed = resp.parsed_output.items

    # Abbinamento per indice, non per posizione: niente lega una risposta
    # alla sua domanda se non l'index/title riecheggiati dal modello, quindi
    # costruiamo una mappa index -> risposta invece di fidarci dell'ordine in
    # cui sono arrivate. Indici fuori intervallo sono ignorati; sui duplicati
    # teniamo la prima occorrenza (una seconda risposta per lo stesso indice
    # non deve poter sovrascrivere silenziosamente la prima).
    by_index: dict[int, _Review] = {}
    for r in parsed:
        if r.index < 0 or r.index >= len(items) or r.index in by_index:
            continue
        by_index[r.index] = r

    out: list[dict] = []
    matched = 0
    for k, it in enumerate(items):
        r = by_index.get(k)
        if r is not None:
            expected_title = it.get("title")
            if expected_title is not None and (
                    _normalize_title_for_match(r.title)
                    != _normalize_title_for_match(expected_title)):
                # Il titolo riecheggiato non corrisponde a quello della
                # traccia a quell'indice: risposta sospetta (probabile
                # slittamento), la scartiamo invece di fidarcene.
                r = None
        if r is None:
            out.append({"genre": None, "confidence": "low"})
            continue
        matched += 1
        conf = "high" if r.confidence == "high" else "low"
        out.append({"genre": r.genre or None, "confidence": conf})

    if matched * 2 < len(items):
        # Meno della metà delle risposte ha superato la guardia indice/titolo:
        # non è un caso di poche tracce genuinamente incerte, è il sintomo di
        # un batch sistematicamente disallineato (slittamento posizionale).
        # Solleviamo invece di restituire degli unresolved silenziosi: il
        # chiamante (genre_review.review) tratta un'eccezione come batch
        # fallito e NON marca i file come revisionati, così vengono
        # ripassati alla prossima passata invece di perdere il lavoro.
        raise AiReviewError(
            "review_genres: meno della metà delle risposte del modello ha "
            "superato il controllo di coerenza indice/titolo — probabile "
            "disallineamento del batch (slittamento posizionale); scarto "
            "l'intero batch invece di rischiare di scrivere il genere "
            "sbagliato sulla traccia sbagliata")
    return out
