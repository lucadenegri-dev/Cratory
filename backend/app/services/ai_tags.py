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
    "SCALA DI EVIDENZA: usa il livello più specifico per cui esiste evidenza "
    "reale, nell'ordine traccia → release/album → artista, e non fermarti al "
    "genere generale dell'artista quando è reperibile evidenza sulla release "
    "specifica. Un artista con discografia eterogenea può avere release di "
    "generi diversi (es. Oneohtrix Point Never ha album ambient, ma anche "
    "album più vicini a progressive/IDM/synthpop): il genere 'tipico' "
    "dell'artista non è una prova sul singolo brano, è solo la sua ultima "
    "spiaggia. Quando l'unica base disponibile è la reputazione generale "
    "dell'artista (nessuna evidenza specifica sulla traccia o sulla release), "
    "dichiaralo con level='artist' invece di spacciarlo per una risposta "
    "certa. IMPORTANTE: per ogni elemento della risposta valorizza SEMPRE index con il "
    "numero che precede la traccia (es. per la riga '3. ...' usa index=3) e "
    "title con la parte iniziale di quella riga così com'è scritta, cioè "
    "'Artista - Titolo' per intero (tutto ciò che segue il numero e precede "
    "il primo '|'): servono a verificare che la risposta sia abbinata alla "
    "traccia giusta e non a quella vicina, quindi non ometterli e non "
    "riecheggiare la parte iniziale di un'altra riga. Non serve rispondere "
    "nello stesso ordine delle tracce, ma ogni risposta deve riportare "
    "l'index e il title corretti della traccia a cui si riferisce. Valorizza "
    "level con il livello di evidenza effettivamente usato per decidere: "
    "'track' se hai trovato evidenza sulla traccia specifica, 'release' se "
    "l'evidenza più specifica trovata riguarda la release/l'album, 'artist' "
    "se ti sei basato solo sulla reputazione generale dell'artista. Imposta "
    "confidence='high' se sei sicuro, "
    "'low' se incerto. Se non riesci a determinare il genere metti genre a "
    "null; non inventare valori spazzatura."
)


# Istruzione aggiuntiva iniettata nel prompt SOLO in modalità "cerca sempre"
# (tracce senza alcun candidato dai provider): a differenza del prompt
# comune, che autorizza la ricerca "quando l'evidenza non basta", qui il
# modello va istruito a cercare — per queste tracce non esiste alternativa
# documentata, quindi rispondere a memoria è esattamente il comportamento che
# vogliamo impedire. Composta in coda al prompt comune (non lo duplica).
_ALWAYS_SEARCH_INSTRUCTION = (
    "ATTENZIONE: per le tracce di questo batch i provider (MusicBrainz/"
    "Discogs) non hanno restituito NESSUN candidato: non hai alcuna "
    "evidenza documentata da cui partire. DEVI cercare sul web prima di "
    "rispondere, non affidarti alla sola memoria/reputazione dell'artista. "
    "Se la ricerca non produce nulla di solido, è preferibile mettere "
    "genre a null piuttosto che indovinare dal nome dell'artista."
)


def _build_review_prompt(*, always_search: bool) -> str:
    """Compone il prompt di revisione: il testo comune, più — in modalità
    'cerca sempre' — l'istruzione aggiuntiva che spinge a cercare invece di
    rispondere a memoria. Componimento per concatenazione, non duplicazione
    del prompt comune (è lungo)."""
    if always_search:
        return _REVIEW_PROMPT + "\n\n" + _ALWAYS_SEARCH_INSTRUCTION
    return _REVIEW_PROMPT


class _Review(BaseModel):
    index: int = -1
    title: str | None = None
    genre: str | None = None
    confidence: str = "low"
    level: str | None = None


class _Reviews(BaseModel):
    items: list[_Review]


# Livelli di evidenza ammessi per il campo `level`, in ordine di specificità
# decrescente (vedi scala nel prompt sopra). Un valore fuori da questo
# vocabolario (o assente) viene normalizzato a None invece di propagarsi.
_EVIDENCE_LEVELS = {"track", "release", "artist"}


def _normalize_title_for_match(title: str | None) -> str:
    """Forma normalizzata di un titolo per il confronto della guardia: solo
    caratteri alfanumerici in minuscolo, così maiuscole/minuscole, spazi,
    punteggiatura e apostrofi (dritti o tipografici, es. '’') non causano
    falsi scarti."""
    if title is None:
        return ""
    return "".join(ch.lower() for ch in title if ch.isalnum())


# Il modello, nonostante il prompt chieda "Artista - Titolo", tende a volte a
# riecheggiare l'intera testa della riga passata (che include l'artista)
# invece del solo titolo dell'item: un confronto per uguaglianza scarterebbe
# quindi anche risposte perfettamente allineate. Usiamo il contenimento
# (normalizzato contro normalizzato) così "oneohtrixpointneverreplica"
# continua a "contenere" "replica". Sotto questa soglia di lunghezza il
# contenimento smette di essere prova affidabile: un titolo corto come
# "Acid" (4 caratteri normalizzati) può comparire per puro caso dentro la
# riga di una traccia completamente diversa (es. "rataxes - Acid Face"),
# quindi sotto soglia rinunciamo al confronto testuale e ci affidiamo al
# solo index.
_MIN_NORMALIZED_TITLE_LEN_FOR_GUARD = 5


def _titles_match_for_guard(echoed_head: str | None, expected_title: str) -> bool:
    """True se la testa di riga riecheggiata dal modello è compatibile col
    titolo atteso per quell'indice: uguaglianza o contenimento reciproco
    (dopo normalizzazione), oppure titolo troppo corto per un confronto
    affidabile (vedi soglia sopra)."""
    norm_expected = _normalize_title_for_match(expected_title)
    if len(norm_expected) < _MIN_NORMALIZED_TITLE_LEN_FOR_GUARD:
        return True
    norm_echoed = _normalize_title_for_match(echoed_head)
    return norm_expected in norm_echoed or norm_echoed in norm_expected


class AiReviewError(Exception):
    """Il batch non ha prodotto un output strutturato (parsing fallito, oppure
    il turno è stato consumato interamente dalla ricerca web senza arrivare a
    un `parsed_output`). Va distinto dal caso in cui l'AI risponde ma non sa
    decidere un singolo item (quello resta un `genre: None` legittimo): qui
    non abbiamo ricevuto alcuna risposta valida, quindi il chiamante
    (genre_review.review) deve trattare l'intero batch come fallito invece di
    marcare i file come revisionati."""


def review_genres(items: list[dict], *, max_web_searches: int = 3,
                  always_search: bool = False) -> list[dict]:
    """Rivede il genere di un batch di tracce con contesto provider e web search.
    items: [{'artist','title','album','label','current_genre','candidates'}];
    ritorna [{'genre': str|None, 'confidence': 'high'|'low',
    'level': 'track'|'release'|'artist'|None}] allineato per indice.

    max_web_searches: tetto di ricerche web per QUESTA chiamata (finisce in
    max_uses del tool); a 0 il tool web_search non viene passato affatto
    (nessuna ricerca possibile), invece di essere passato con un tetto zero.
    always_search: se True, il prompt include l'istruzione aggiuntiva che
    impone di cercare (batch di tracce senza candidati dai provider); il
    default preserva il comportamento preesistente (autorizzata ma non
    imposta, tetto 3) per chi chiama la funzione senza questi parametri."""
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
    prompt = _build_review_prompt(always_search=always_search)
    kwargs: dict = dict(
        model=_MODEL,
        max_tokens=4096,
        messages=[{"role": "user",
                   "content": f"{prompt}\n\n" + "\n".join(lines)}],
        output_format=_Reviews,
    )
    if max_web_searches > 0:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": max_web_searches}]
    resp = client.messages.parse(**kwargs)
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
            if expected_title is not None and not _titles_match_for_guard(
                    r.title, expected_title):
                # La testa di riga riecheggiata non è compatibile col titolo
                # della traccia a quell'indice: risposta sospetta (probabile
                # slittamento), la scartiamo invece di fidarcene.
                r = None
        if r is None:
            out.append({"genre": None, "confidence": "low", "level": None})
            continue
        matched += 1
        conf = "high" if r.confidence == "high" else "low"
        level = r.level if r.level in _EVIDENCE_LEVELS else None
        if level == "artist":
            # Effetto alone dell'artista: la ricerca ha mostrato che è qui che
            # si concentrano gli errori (il modello marca 'high' anche quando
            # sbaglia, scivolando sul genere più famoso associato al nome
            # invece che sulla release/traccia specifica). Quando l'unica
            # base è la reputazione generale dell'artista la confidenza va
            # forzata a bassa nel codice, non lasciata al giudizio del
            # modello.
            conf = "low"
        out.append({"genre": r.genre or None, "confidence": conf, "level": level})

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
