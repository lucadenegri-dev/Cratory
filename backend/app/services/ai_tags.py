"""Estrazione AI di artist/title dai nomi file (Claude Haiku). Import lazy: il
modulo si carica senza il pacchetto `anthropic`; solo suggest() lo richiede.
Mockabile nei test (monkeypatch su ai_tags.suggest)."""

import logging
import os
import re

from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    "'Tech House', 'Acid Techno', 'Drum & Bass'). Se una fonte (es. Beatport, "
    "Discogs) riporta una lista o un tag composto — esempio reale osservato: "
    "'Breaks / Breakbeat / UK Bass' — NON restituire la lista così com'è: "
    "scegli tu il singolo genere più specifico tra quelli elencati. Il valore "
    "restituito non deve mai contenere separatori di elenco (virgola, barra, "
    "punto e virgola). I candidati dei provider "
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
    "null; non inventare valori spazzatura. REQUISITO SULLA FORMA DELLA "
    "RISPOSTA: la risposta deve contenere ESATTAMENTE un elemento per "
    "ciascuna delle tracce numerate qui sotto, anche quando decidi di "
    "lasciare genre a null — in quel caso l'elemento va comunque incluso, "
    "non omesso. Una lista vuota, o con meno elementi delle tracce elencate, "
    "non è una risposta valida."
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
    "genre a null piuttosto che indovinare dal nome dell'artista. Attenzione: "
    "'genere non determinato' e 'traccia omessa dalla risposta' sono due "
    "cose diverse, e solo la prima è accettabile — anche quando la ricerca "
    "non porta a nulla di solido, l'elemento per quella traccia va comunque "
    "incluso nella risposta, con genre a null."
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


# Rete di sicurezza: caso osservato dal vivo (Djrum - Waxcap), 2 esecuzioni su
# 3 identiche, il modello ha restituito 'Breaks / Breakbeat / UK Bass' —
# copiata pari pari la stringa di tag composita di Beatport — nonostante il
# prompt chieda esplicitamente UN solo genere. Trattiamo come separatore di
# ELENCO barra, virgola, punto e virgola e trattino verticale: non qualunque
# punteggiatura, altrimenti generi legittimi come 'Drum & Bass', 'Tech House'
# o 'Hi-NRG' (che contengono '&' e '-' ma non sono liste) verrebbero troncati
# per errore. Il trattino singolo NON è incluso: è usato dentro nomi di
# genere legittimi (Hi-NRG) e non come separatore da queste fonti.
_GENRE_LIST_SEP_RE = re.compile(r"[,/;|]")


def _reduce_compound_genre(genre: str | None) -> str | None:
    """Se `genre` contiene un separatore di elenco, lo riduce al primo
    componente invece di scartarlo: nelle fonti che restituiscono liste
    ordinate (Discogs styles, tag compositi Beatport) il primo elemento è la
    scelta più specifica — la stessa convenzione già adottata da
    DiscogsMetaClient.lookup, che prende styles[0]. Nessun separatore -> il
    valore torna invariato."""
    if genre is None:
        return None
    if not _GENRE_LIST_SEP_RE.search(genre):
        return genre
    first = _GENRE_LIST_SEP_RE.split(genre, maxsplit=1)[0].strip()
    return first or None


class AiReviewError(Exception):
    """Il batch non ha prodotto un output strutturato (parsing fallito, oppure
    il turno è stato consumato interamente dalla ricerca web senza arrivare a
    un `parsed_output`). Va distinto dal caso in cui l'AI risponde ma non sa
    decidere un singolo item (quello resta un `genre: None` legittimo): qui
    non abbiamo ricevuto alcuna risposta valida, quindi il chiamante
    (genre_review.review) deve trattare l'intero batch come fallito invece di
    marcare i file come revisionati.

    `web_searches`: totale delle ricerche web consumate nei tentativi già
    effettuati per questo batch (Fix 4) — un batch che fallisce può aver
    comunque speso ricerche a pagamento prima di arrendersi, e il chiamante
    non deve perderne il conteggio solo perché l'esito non è utilizzabile."""

    def __init__(self, message: str, *, web_searches: int = 0):
        super().__init__(message)
        self.web_searches = web_searches


class _ReviewResults(list):
    """list[dict] — la stessa forma di ritorno di sempre, allineata per
    indice — con un attributo aggiuntivo `web_searches` (Fix 4): il numero
    di ricerche web effettivamente eseguite dal modello per produrre QUESTO
    batch, sommato su tutti i tentativi. Sottoclasse di list invece di
    cambiare la forma del valore restituito: chi confronta il risultato con
    `== [...]` o lo itera/indicizza (guardia esistente, test) continua a
    funzionare invariato — list.__eq__ confronta gli elementi, non il tipo.
    Chi vuole il conteggio lo legge con `getattr(risultato, 'web_searches',
    0)`, così un ai_fn iniettato nei test che ritorna una list semplice
    (senza l'attributo) continua a funzionare, riportando 0 ricerche invece
    di sollevare."""
    web_searches: int = 0


def _extract_web_search_count(resp) -> int:
    """Numero di ricerche web eseguite in QUESTA risposta, da
    response.usage.server_tool_use.web_search_requests. Accesso difensivo:
    fake/risposte prive di questi attributi (nei test, o quando il tool
    web_search non è stato passato) danno 0 invece di sollevare."""
    usage = getattr(resp, "usage", None)
    stu = getattr(usage, "server_tool_use", None)
    return getattr(stu, "web_search_requests", 0) or 0


def _match_reviews_to_items(parsed: list["_Review"],
                             items: list[dict]) -> tuple[list[dict], int]:
    """Abbina le risposte del modello (`parsed`, l'`items` di UN tentativo di
    `_Reviews`) alle tracce del batch, per indice con guardia sul titolo
    riecheggiato. Ritorna (output allineato per indice — 'genre'/'confidence'/
    'level' per ogni traccia, unresolved dove non c'è risposta valida —,
    numero di tracce abbinate con successo). Non solleva: la decisione se il
    risultato è sufficiente spetta al chiamante (review_genres), che la usa
    sia per decidere il ritentativo sia per la guardia finale."""
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
        genre = _reduce_compound_genre(r.genre or None)
        out.append({"genre": genre, "confidence": conf, "level": level})
    return out, matched


# Tetto di tentativi per un batch: la prima chiamata più UN solo ritentativo
# quando la risposta è vuota/troppo corta, non un ciclo (vedi motivazione nel
# corpo di review_genres).
_MAX_REVIEW_ATTEMPTS = 2


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
    imposta, tetto 3) per chi chiama la funzione senza questi parametri.

    Se la risposta del modello è vuota o troppo corta per essere credibile
    (vedi soglia sotto), OPPURE se non produce alcun output strutturato
    (parsing fallito o turno consumato interamente dalla ricerca web — vedi
    AiReviewError), la richiesta viene ritentata UNA sola volta prima di
    sollevare: osservato dal vivo che lo stesso batch, a distanza di
    chiamate identiche, può tornare con 0 elementi invece dei 3 attesi (zero
    ricerche eseguite) pur avendo risposto correttamente al giro precedente
    e a quello successivo — un problema di quella singola risposta, non del
    batch. Il secondo caso (parsed_output None) è reso più probabile dal
    budget di ricerca dei sotto-batch bisognosi (fino a len(sub) ricerche web
    in una sola chiamata): più ricerche significa più probabilità che il
    turno le esaurisca senza arrivare a un output strutturato. Il
    ritentativo non ha un costo aggiuntivo netto: un batch scartato viene
    comunque ripassato alla prossima passata di revisione (stesso lavoro,
    rifatto più tardi), ma ritentando subito lo si completa ORA invece di
    rimandarlo, così le tracce non restano indietro — ed evita che un batch
    deterministico rifallisca identico, bruciando le stesse ricerche ad ogni
    passata senza mai marcare i suoi file."""
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
        # 4096 era troppo stretto: un sotto-batch bisognoso può autorizzare
        # fino a len(sub) ricerche web (10 al massimo, batch_size di
        # default) in UNA sola chiamata, e ogni ricerca aggiunge query +
        # risultati al turno prima ancora di arrivare all'output strutturato
        # finale (10 item con index/title/genre/confidence/level, poche
        # centinaia di token). "Turno consumato dalla ricerca web" (Fix 1) è
        # esattamente il fallimento che un tetto basso rende probabile in
        # quello scenario. Si paga l'output EFFETTIVAMENTE prodotto, non il
        # tetto, quindi alzarlo non ha costo: 32000 lascia margine ampio
        # rispetto al caso limite (10 ricerche + 10 item strutturati) pur
        # restando a metà degli 64K di output massimi di Claude Haiku 4.5.
        max_tokens=32000,
        messages=[{"role": "user",
                   "content": f"{prompt}\n\n" + "\n".join(lines)}],
        output_format=_Reviews,
    )
    if max_web_searches > 0:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": max_web_searches}]

    total_web_searches = 0
    for attempt in range(1, _MAX_REVIEW_ATTEMPTS + 1):
        resp = client.messages.parse(**kwargs)
        total_web_searches += _extract_web_search_count(resp)
        if resp.parsed_output is None:
            # Nessun output strutturato per l'intero batch (parsing fallito o
            # turno esaurito in ricerca web): caso distinto dalla lista
            # `items` vuota/corta gestita sotto (qui non c'è proprio una
            # risposta da valutare). Fix 1: ritentiamo come per il caso
            # sotto, con la stessa disciplina (un solo ritentativo
            # complessivo — _MAX_REVIEW_ATTEMPTS è condiviso, non c'è un
            # tetto separato per tipo di fallimento, quindi nessuna
            # possibilità di catena).
            if attempt < _MAX_REVIEW_ATTEMPTS:
                logger.warning(
                    "review_genres: nessun output strutturato al tentativo "
                    "%d/%d (parsing fallito o turno consumato dalla ricerca "
                    "web) — ritento la stessa richiesta",
                    attempt, _MAX_REVIEW_ATTEMPTS)
                continue
            logger.warning(
                "review_genres: nessun output strutturato anche al "
                "tentativo %d/%d — abbandono il batch",
                attempt, _MAX_REVIEW_ATTEMPTS)
            raise AiReviewError(
                "review_genres: nessun output strutturato ricevuto dal modello "
                "(parsing fallito o turno consumato dalla ricerca web), "
                "anche dopo un ritentativo",
                web_searches=total_web_searches)
        out, matched = _match_reviews_to_items(resp.parsed_output.items, items)

        # Soglia: meno della metà delle risposte ha superato la guardia
        # indice/titolo. È la STESSA soglia usata sotto per decidere se
        # arrendersi (vedi commento sulla guardia finale) — qui la applichiamo
        # anche per decidere se vale la pena ritentare, perché il caso
        # osservato dal vivo (items vuota) è semplicemente il punto più
        # estremo di questa stessa condizione: matched=0 non può che stare
        # sotto la metà. Un'astensione motivata (item presenti e allineati
        # ma genre=None) NON tocca questa soglia: `matched` conta le tracce
        # abbinate per indice/titolo, non quelle con un genere trovato, quindi
        # "non so" resta una risposta valida e non fa scattare il
        # ritentativo.
        if matched * 2 >= len(items):
            result = _ReviewResults(out)
            result.web_searches = total_web_searches
            return result

        if attempt < _MAX_REVIEW_ATTEMPTS:
            logger.warning(
                "review_genres: risposta insufficiente al tentativo %d/%d "
                "(%d/%d tracce abbinate) — ritento la stessa richiesta",
                attempt, _MAX_REVIEW_ATTEMPTS, matched, len(items))
            continue

        logger.warning(
            "review_genres: risposta insufficiente anche al tentativo %d/%d "
            "(%d/%d tracce abbinate) — abbandono il batch",
            attempt, _MAX_REVIEW_ATTEMPTS, matched, len(items))
        # Meno della metà delle risposte ha superato la guardia indice/titolo,
        # anche dopo un ritentativo: non è un caso di poche tracce
        # genuinamente incerte, è il sintomo di una risposta vuota/troncata o
        # di un batch sistematicamente disallineato (slittamento
        # posizionale). Solleviamo invece di restituire degli unresolved
        # silenziosi: il chiamante (genre_review.review) tratta un'eccezione
        # come batch fallito e NON marca i file come revisionati, così
        # vengono ripassati alla prossima passata invece di perdere il
        # lavoro.
        raise AiReviewError(
            "review_genres: meno della metà delle risposte del modello ha "
            "superato il controllo di coerenza indice/titolo, anche dopo un "
            "ritentativo — probabile risposta vuota/troncata o "
            "disallineamento del batch (slittamento posizionale); scarto "
            "l'intero batch invece di rischiare di scrivere il genere "
            "sbagliato sulla traccia sbagliata",
            web_searches=total_web_searches)
