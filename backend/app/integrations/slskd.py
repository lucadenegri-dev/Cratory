"""Client per il daemon Soulseek headless slskd (REST API v0).

slskd fa la rete P2P (login, peer, code); Cratory orchestra. Principalmente un
downloader; la condivisione della libreria è un opt-in esplicito (flag in Settings,
vedi `services/slskd_shares.py` che scrive `shares.directories` nello YAML).
Confermare gli endpoint contro lo Swagger del proprio slskd (<SLSKD_URL>/swagger).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core import runtime_settings
from app.integrations._http import ClosableHttpClient, get_with_retries, raise_for_status

logger = logging.getLogger(__name__)

BASE = "/api/v0"

# slskd serializza nel proprio processo le due POST che avviano un lavoro, e
# non mette in attesa chi arriva secondo: risponde 429 all'istante ("Only one
# concurrent operation is permitted"), perche' prova a prendere il semaforo
# senza attendere (`Wait(0)`).
#
#   SearchesController   SemaphoreSlim(1, 1)  ->  POST /searches
#   TransfersController  SemaphoreSlim(2, 2)  ->  POST /transfers/downloads/{u}
#
# Cratory ne fa piu' di una alla volta di mestiere: il pool della coda lavora
# `download_slots` item in parallelo (tre di default) e ogni worker comincia
# proprio con una ricerca — quindi partendo insieme, come fanno quando si
# accoda una playlist, due su tre prendevano un 429 prima ancora di provare a
# scaricare. I cancelli qui sotto rispecchiano i tetti del daemon, cosi' la
# richiesta di troppo aspetta il suo turno invece di essere rifiutata.
#
# Sono di modulo e non del client perche' il tetto e' del daemon, non della
# connessione: i client si creano e si buttano per ogni item (`run_item`), e
# un cancello per istanza non conterebbe nulla. Un solo processo uvicorn,
# quindi un lock in memoria basta — la stessa assunzione della coda
# (`download_queue._claim_lock`).
_SEARCH_GATE = threading.Semaphore(1)
_ENQUEUE_GATE = threading.Semaphore(2)

# Il cancello copre le richieste di Cratory, non quelle di chiunque altro:
# la web UI di slskd, aperta sull'altro monitor, occupa lo stesso semaforo.
# Per quel residuo si ritenta, con attesa crescente e un tetto: un 429 che
# sopravvive a tutti i tentativi non e' piu' un incidente di traffico ed e'
# trattato come infrastruttura (vedi `slskd_unreachable`).
THROTTLE_RETRIES = 4      # tentativi totali, non aggiuntivi
THROTTLE_BACKOFF = 0.25   # secondi, raddoppia a ogni rifiuto: 0.25, 0.5, 1.0


class SlskdError(Exception):
    """Errore di comunicazione con slskd."""


class SlskdNotConfigured(SlskdError):
    """SLSKD_URL non impostato."""


@dataclass
class SlskdFile:
    """Un file candidato restituito da una ricerca slskd."""

    username: str
    filename: str
    size: int | None
    bitrate: int | None
    length: int | None
    has_free_slot: bool
    queue_length: int | None
    # Velocita' di upload dichiarata dall'utente (byte/s): chi serve veloce e' preferibile.
    upload_speed: int | None = None

    @property
    def extension(self) -> str:
        return Path(self.filename.replace("\\", "/")).suffix.lower().lstrip(".")


class SlskdClient(ClosableHttpClient):
    def __init__(self, url: str | None = None, api_key: str | None = None,
                 http: httpx.Client | None = None):
        self.url = (url if url is not None else runtime_settings.slskd_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else runtime_settings.slskd_api_key()
        if not self.url:
            raise SlskdNotConfigured("SLSKD_URL mancante in backend/.env.")
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        self.http = http or httpx.Client(timeout=30, headers=headers)

    def _get(self, path: str, params: dict | None = None):
        r = get_with_retries(self.http, f"{self.url}{BASE}{path}",
                             error_cls=SlskdError, params=params)
        # Niente rate_limit_message: slskd non ha mai distinto 429 da un
        # generico 4xx/5xx, a differenza di lastfm/discogs (comportamento
        # preesistente, invariato). r.json() non e' avvolto in un errore
        # tipizzato: idem, il ValueError grezzo su risposta non-JSON e'
        # comportamento preesistente.
        raise_for_status(r, SlskdError, name="slskd")
        return r.json()

    def _post(self, path: str, json=None):
        try:
            r = self.http.post(f"{self.url}{BASE}{path}", json=json)
        except httpx.HTTPError as exc:
            raise SlskdError(f"slskd POST {path} fallita: {exc}") from exc
        raise_for_status(r, SlskdError, name="slskd")
        return r.json() if r.content else {}

    def _post_throttled(self, path: str, gate: threading.Semaphore, json=None):
        """`_post` per gli endpoint che slskd serializza (vedi i cancelli in
        cima al modulo): si aspetta il proprio turno, e un 429 di un altro
        client si ritenta invece di risalire al chiamante.

        L'attesa fra un tentativo e l'altro sta FUORI dal cancello: dormirci
        dentro bloccherebbe anche chi e' in fila per un turno che il daemon
        avrebbe gia' libero.
        """
        attesa = THROTTLE_BACKOFF
        for tentativo in range(THROTTLE_RETRIES):
            with gate:
                try:
                    return self._post(path, json=json)
                except SlskdError as exc:
                    ultimo = tentativo == THROTTLE_RETRIES - 1
                    if getattr(exc, "status_code", None) != 429 or ultimo:
                        raise
                    logger.warning("slskd ha strozzato POST %s (tentativo %d/%d), "
                                   "riprovo fra %.2fs", path, tentativo + 1,
                                   THROTTLE_RETRIES, attesa)
            time.sleep(attesa)
            attesa *= 2

    def _put(self, path: str, json=None):
        try:
            r = self.http.put(f"{self.url}{BASE}{path}", json=json)
        except httpx.HTTPError as exc:
            raise SlskdError(f"slskd PUT {path} fallita: {exc}") from exc
        raise_for_status(r, SlskdError, name="slskd")
        return r.json() if r.content else {}

    def _delete(self, path: str, params: dict | None = None):
        try:
            r = self.http.delete(f"{self.url}{BASE}{path}", params=params)
        except httpx.HTTPError as exc:
            raise SlskdError(f"slskd DELETE {path} fallita: {exc}") from exc
        raise_for_status(r, SlskdError, name="slskd")
        return r.json() if r.content else {}

    def server_state(self) -> dict:
        """Stato della connessione alla rete Soulseek (GET /server): flag booleani
        `isConnected`/`isLoggedIn`/`isConnecting`/`isTransitioning` e `state`."""
        return self._get("/server")

    def connect(self) -> None:
        """Connette il client alla rete Soulseek (PUT /server)."""
        self._put("/server")

    def disconnect(self) -> None:
        """Disconnette il client dalla rete Soulseek (DELETE /server)."""
        self._delete("/server")

    def rescan_shares(self) -> None:
        """Forza un rescan delle share (PUT /shares). Usato dopo che Cratory ha
        scritto `shares.directories` in slskd.yml (le share non sono mutabili via
        API a runtime, solo dallo YAML): il rescan le rende effettive senza
        aspettare l'intervallo di retention."""
        self._put("/shares")

    def soulseek_username(self) -> str | None:
        """Username dell'account Soulseek configurato in slskd (GET /options).

        La password e' mascherata da slskd e non ci interessa: a Cratory serve
        solo lo username per mostrare "connesso come ...". Sezione o campo
        assenti -> None (nessun KeyError)."""
        options = self._get("/options") or {}
        soulseek = options.get("soulseek") or {}
        return soulseek.get("username")

    def search(self, artist: str, title: str, *, response_limit: int = 30,
               search_timeout_ms: int = 6000, max_wait: float = 15.0,
               poll_interval: float = 0.5) -> list[SlskdFile]:
        """Avvia una ricerca slskd e attende il COMPLETAMENTO, poi legge le risposte.

        slskd popola `GET /searches/{id}/responses` solo a ricerca completa: mentre e'
        in corso ritorna lista vuota anche se `responseCount` cresce. Per chiudere in
        fretta e in modo affidabile si passano parametri per-ricerca: `responseLimit`
        (le ricerche popolari completano appena raggiunto, in 1-2s) e `searchTimeout`
        (backstop per quelle rare/assenti). Si attende `isComplete` con tetto `max_wait`
        (> search_timeout, margine di rete). Un tetto troppo basso o l'attesa del solo
        numero di risposte restituiscono liste vuote anche quando i file esistono.

        Uscita anticipata: se `responseCount` smette di crescere per due poll
        consecutivi (ed e' gia' > 0) si esce senza attendere `isComplete` ne'
        il tetto `max_wait` — le ricerche popolari si stabilizzano ben prima
        di essere marcate complete, e attendere oltre e' solo latenza persa
        per il chiamante (es. l'endpoint /candidates, sincrono sulla request).
        Al termine la ricerca viene cancellata sul daemon (best-effort): senza
        pulizia le ricerche si accumulano indefinitamente.
        """
        text = f"{artist} {title}".strip()
        if not text:
            return []
        created = self._post_throttled("/searches", _SEARCH_GATE, json={
            "searchText": text,
            "searchTimeout": search_timeout_ms,
            "responseLimit": response_limit,
        })
        search_id = created.get("id")
        if not search_id:
            raise SlskdError("slskd: ricerca senza id.")
        waited = 0.0
        prev_count: int | None = None
        stable_polls = 0
        while waited < max_wait:
            state = self._get(f"/searches/{search_id}")
            if state.get("isComplete") or "completed" in str(state.get("state", "")).lower():
                break
            count = state.get("responseCount")
            if isinstance(count, int):
                if prev_count is not None and count == prev_count:
                    stable_polls += 1
                    if count > 0 and stable_polls >= 2:
                        break
                else:
                    stable_polls = 0
                prev_count = count
            time.sleep(poll_interval)
            waited += poll_interval
        responses = self._get(f"/searches/{search_id}/responses")
        files = self._flatten_responses(responses)
        try:
            self._delete(f"/searches/{search_id}")
        except SlskdError as exc:
            logger.warning("Cancellazione ricerca slskd %s fallita: %s", search_id, exc)
        return files

    def enqueue_download(self, file: "SlskdFile") -> None:
        self._post_throttled(f"/transfers/downloads/{file.username}", _ENQUEUE_GATE,
                             json=[{"filename": file.filename, "size": file.size or 0}])

    def transfer_state(self, username: str, filename: str) -> dict | None:
        """Stato del transfer per (username, filename).

        Senza cancellazione dei transfer abbandonati (`remove=false` di default,
        vedi `cancel_download`) lo storico di un utente puo' contenere piu' voci
        con lo stesso filename (un vecchio tentativo cancellato + uno nuovo appena
        accodato). Si preferisce una voce ATTIVA (in corso) se presente — così un
        transfer live non viene mascherato da una vecchia voce terminale
        (cancelled/failed/completed), a prescindere dall'ordine con cui slskd le
        restituisce; in assenza di voci attive si tiene l'ultima corrispondenza.
        Se il payload espone anche uno username per-file (alcune versioni lo
        fanno), lo si rispetta come filtro aggiuntivo.
        """
        data = self._get(f"/transfers/downloads/{username}")
        match = None
        active = None
        for directory in data.get("directories") or []:
            for f in directory.get("files") or []:
                if f.get("filename") != filename:
                    continue
                file_username = f.get("username")
                if file_username is not None and file_username != username:
                    continue
                match = f
                if classify_transfer_state(f.get("state") or "") == "in_progress":
                    active = f
        return active or match

    def cancel_download(self, username: str, transfer_id: str, *, remove: bool = False) -> None:
        """Annulla un transfer nel daemon (best-effort lato chiamante).

        `remove=False` di default: annulla ma lascia la voce nello storico
        (coerente con lo stile del client, che non forza la rimozione a meno
        che non sia esplicitamente richiesta).
        """
        self._delete(f"/transfers/downloads/{username}/{transfer_id}",
                     params={"remove": remove})

    @staticmethod
    def _flatten_responses(responses) -> list[SlskdFile]:
        out: list[SlskdFile] = []
        for resp in responses or []:
            username = resp.get("username") or ""
            has_slot = bool(resp.get("hasFreeUploadSlot"))
            queue = resp.get("queueLength")
            speed = resp.get("uploadSpeed")
            for f in resp.get("files") or []:
                out.append(SlskdFile(
                    username=username,
                    filename=f.get("filename") or "",
                    size=f.get("size"),
                    bitrate=f.get("bitRate"),
                    length=f.get("length"),
                    has_free_slot=has_slot,
                    queue_length=queue,
                    upload_speed=speed,
                ))
        return out


def slskd_configured() -> bool:
    """Vero se URL e cartella di download sono valorizzati. Attenzione: dice
    che slskd e' *impostato*, non che il daemon sia acceso — per quello vedi
    `slskd_unreachable`, che lo scopre solo provando."""
    return bool(runtime_settings.slskd_url() and runtime_settings.slskd_download_dir())


# Frammenti che, dentro un 409, dicono "il daemon e' vivo ma non e' collegato
# alla rete Soulseek". slskd risponde cosi' a POST /searches in quello stato:
# "must be connected (currently: Disconnected)". E' la condizione piu' frequente
# dopo un riavvio o un blip di rete, e non ha niente a che vedere con la singola
# traccia.
#
# I frammenti devono parlare del SERVER e di nient'altro: `disconnected` e
# `not connected` da soli catturavano anche un 409 su un PEER offline ("user
# bob is disconnected"), che e' colpa del candidato. I due errori non si
# equivalgono. Classificare per difetto (un motivo d'infrastruttura non
# riconosciuto) ha una rete di sicurezza: l'item fallisce, e N fallimenti
# consecutivi con lo stesso motivo aprono l'interruttore del dispatcher.
# Classificare per eccesso non ne ha nessuna: l'item torna in coda con
# `attempts` DECREMENTATO, quindi non fallisce mai, il pool va in pausa, il
# riaggancio lo ripesca e si ricomincia — all'infinito, senza che nulla lo
# conti. Meglio quindi mancare una formulazione nuova che allargare la rete.
_NON_COLLEGATO = ("must be connected", "currently: disconnected")


def slskd_unreachable(exc: BaseException) -> bool:
    """Vero se l'errore dice "il daemon non risponde o e' malconfigurato",
    falso se dice "questa traccia/richiesta non va bene cosi'".

    I tipi di questo modulo non bastano a distinguerli: `SlskdError` copre sia
    la connessione che non si apre sia un 4xx/5xx di un daemon vivo e vegeto.
    Due segnali, nessuno dei quali richiede eccezioni nuove:

    - la *causa*: gli errori di trasporto httpx (connessione rifiutata, DNS,
      timeout) risalgono come `__cause__` sia dai verbi POST/PUT/DELETE qui
      sopra sia dal retry di `_http._request_with_retries` usato dalle GET;
    - lo *status code*, che `raise_for_status` attacca come `.status_code`
      sull'eccezione che solleva (vedi `_http.raise_for_status`): 401/403
      (chiave API sbagliata o ruotata) e ogni 5xx sono un daemon vivo che
      risponde male — infrastruttura quanto una connessione rifiutata, e con
      lo stesso danno se non trattati come tale (un riaggancio che ripesca un
      daemon rotto brucerebbe l'intera coda). Il 429 e' il tetto di
      concorrenza del daemon, e arriva qui solo dopo che `_post_throttled`
      ha atteso il proprio turno e ritentato invano (vedi i cancelli in cima
      al modulo): non e' piu' un incidente di traffico ma un daemon che non
      e' in grado — quanto un 503, e non colpa della traccia. Non puo'
      incantarsi, perche' il semaforo di slskd si libera in un `finally`, e
      finche' non lo fa e' il raffreddamento dell'interruttore a diradare i
      tentativi. Il 409 e' il caso ambiguo: da solo direbbe "questa richiesta
      non va bene", ma quello che slskd manda su `POST /searches` a daemon
      scollegato ("must be connected (currently: Disconnected)") e'
      infrastruttura pura — con 300 item in coda, trattarlo
      come colpa della traccia li marcherebbe tutti `failed` e scriverebbe
      l'esito su 300 tracce. Si guarda quindi il testo (vedi `_NON_COLLEGATO`);
      gli altri 409 restano un fallimento della singola richiesta.

    `SlskdNotConfigured` (URL mancante) e' anch'essa infrastruttura: mai
    colpa della traccia.

    Chi la usa: la coda download, per decidere se un item va fallito o
    rimesso in attesa (`services/download_runner.py`).
    """
    if isinstance(exc, SlskdNotConfigured):
        return True
    if not isinstance(exc, SlskdError):
        return False
    if isinstance(exc.__cause__, httpx.TransportError):
        return True
    status = getattr(exc, "status_code", None)
    if status == 409:
        testo = str(exc).lower()
        return any(frammento in testo for frammento in _NON_COLLEGATO)
    return status is not None and (status in (401, 403, 429) or status >= 500)


def get_slskd_client() -> SlskdClient:
    if not runtime_settings.slskd_url():
        raise SlskdNotConfigured("SLSKD_URL mancante in backend/.env.")
    return SlskdClient()


def classify_transfer_state(state: str) -> str:
    s = (state or "").lower()
    if any(x in s for x in ("errored", "failed", "cancelled", "canceled",
                            "rejected", "timedout")):
        return "failed"
    if "completed" in s or "succeeded" in s:
        return "completed"
    return "in_progress"
