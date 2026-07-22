"""Helper HTTP condiviso dai provider esterni: retry sugli errori di trasporto.

Gli errori di rete transitori (handshake TLS che cade, connessione resettata,
timeout, lettura interrotta) non devono far crashare un job di enrichment: qui si
ritenta con backoff e, se la rete resta irraggiungibile, si solleva l'eccezione
del provider cosi' il chiamante la gestisce come "traccia non trovata" e prosegue.

Risolve in particolare l'errore osservato su api.getsong.co:
  [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
ovvero il server che chiude la connessione TLS a meta' handshake/lettura.
"""

import logging
import ssl
import time

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = 2      # tentativi aggiuntivi oltre al primo (3 in totale)
DEFAULT_BACKOFF = 0.6    # secondi, crescente: 0.6s, 1.2s, ...


def tls12_context() -> ssl.SSLContext:
    """SSL context limitato a TLS 1.2.

    Workaround per host la cui handshake TLS 1.3 viene interrotta da middlebox
    di rete (DPI / antivirus con scansione HTTPS / firewall) con
    'UNEXPECTED_EOF_WHILE_READING': su TLS 1.2 la connessione si negozia.
    Osservato su musicbrainz.org da rete con ispezione TLS attiva, mentre
    getsong.co e ws.audioscrobbler.com funzionano regolarmente su TLS 1.3.
    """
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def get_with_retries(
    client: httpx.Client,
    url: str,
    *,
    error_cls: type[Exception],
    params: dict | None = None,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
) -> httpx.Response:
    """Esegue una GET ritentando sugli errori di trasporto httpx.

    Ritorna la `httpx.Response` (la gestione degli status code resta al chiamante,
    che ha logiche diverse per 429/503). Solleva `error_cls` se la connessione
    fallisce dopo tutti i tentativi. Eventuali header (es. User-Agent) vanno
    impostati sul client; qui passiamo solo i parametri di query.
    """
    return _request_with_retries(
        lambda: client.get(url, params=params), "GET", url,
        error_cls=error_cls, retries=retries, backoff=backoff,
    )


def _request_with_retries(send, method: str, url: str, *, error_cls, retries, backoff):
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return send()
        except httpx.HTTPError as exc:  # SSL / connessione / lettura / timeout
            last_exc = exc
            if attempt < retries:
                wait = backoff * (attempt + 1)
                logger.warning(
                    "%s %s fallita (tentativo %d/%d): %s — riprovo tra %.1fs",
                    method, url, attempt + 1, retries + 1, exc, wait,
                )
                time.sleep(wait)
    raise error_cls(f"connessione fallita dopo {retries + 1} tentativi ({last_exc})")


def raise_for_status(
    response: httpx.Response,
    error_cls: type[Exception],
    *,
    name: str,
    rate_limit_message: str | None = None,
    text_preview: int = 160,
    context: str = "",
) -> None:
    """Mappa lo status code HTTP sull'errore tipizzato del provider.

    Replica la logica prima duplicata in lastfm/discogs/slskd:
    - 429 con un messaggio dedicato *solo* se il chiamante ne passa uno (lastfm e
      discogs vogliono un errore esplicito di rate-limit; slskd non lo ha mai
      distinto da un generico 4xx/5xx, e questo helper preserva la differenza:
      senza `rate_limit_message` il 429 cade nel ramo generico sotto);
    - qualsiasi altro status >=400 solleva `error_cls` con un messaggio
      "{name} {status}{context}: {testo troncato}", stesso formato usato dai
      client concreti (il parametro `context` copre il " su {method}" di lastfm).

    Non fa nulla (torna None) per le risposte <400: il chiamante prosegue con
    `response.json()` o la propria logica successiva.
    """
    if response.status_code == 429 and rate_limit_message is not None:
        raise error_cls(rate_limit_message)
    if response.status_code >= 400:
        raise error_cls(f"{name} {response.status_code}{context}: {response.text[:text_preview]}")


def parse_json(response: httpx.Response, error_cls: type[Exception], *, message: str):
    """`response.json()` con un errore tipizzato invece del ValueError grezzo.

    Usato da lastfm/discogs, che vogliono distinguere una risposta non-JSON da
    un fallimento di trasporto. slskd non lo usa: chiama `response.json()`
    direttamente, comportamento preesistente che questo refactor non cambia.
    """
    try:
        return response.json()
    except ValueError as exc:
        raise error_cls(message) from exc


def get_json(
    client: httpx.Client,
    url: str,
    *,
    error_cls: type[Exception],
    name: str,
    params: dict | None = None,
    rate_limit_message: str | None = None,
    text_preview: int = 160,
    context: str = "",
    json_error_message: str | None = None,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
):
    """GET + retry di trasporto + mappatura status + parsing JSON, in un colpo.

    Composizione di `get_with_retries` + `raise_for_status` + `parse_json`: il
    "_get" thin condiviso da lastfm e discogs. User-Agent/timeout/auth restano
    sul client (impostati alla costruzione), qui si passano solo i parametri di
    query e i messaggi/testi specifici del provider.
    """
    response = get_with_retries(client, url, params=params, error_cls=error_cls,
                                retries=retries, backoff=backoff)
    raise_for_status(response, error_cls, name=name, rate_limit_message=rate_limit_message,
                      text_preview=text_preview, context=context)
    return parse_json(response, error_cls, message=json_error_message or f"{name}: risposta non JSON")


def post_with_retries(
    client: httpx.Client,
    url: str,
    *,
    json_body: dict,
    error_cls: type[Exception],
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
) -> httpx.Response:
    """Come `get_with_retries`, per le API che parlano solo POST (Bandcamp)."""
    return _request_with_retries(
        lambda: client.post(url, json=json_body), "POST", url,
        error_cls=error_cls, retries=retries, backoff=backoff,
    )


def post_json(
    client: httpx.Client,
    url: str,
    *,
    json_body: dict,
    error_cls: type[Exception],
    name: str,
    rate_limit_message: str | None = None,
    text_preview: int = 160,
    context: str = "",
    json_error_message: str | None = None,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
):
    """POST + retry di trasporto + mappatura status + parsing JSON, in un colpo.

    Gemello di `get_json`: stessa composizione, stessi messaggi, verbo diverso.
    """
    response = post_with_retries(client, url, json_body=json_body, error_cls=error_cls,
                                 retries=retries, backoff=backoff)
    raise_for_status(response, error_cls, name=name, rate_limit_message=rate_limit_message,
                     text_preview=text_preview, context=context)
    return parse_json(response, error_cls, message=json_error_message or f"{name}: risposta non JSON")


class ClosableHttpClient:
    """Mixin per i client che possiedono un `httpx.Client` proprio.

    Le istanze di questi client sono create per-request (una per chiamata router/
    job, mai un singleton condiviso: vedi `DiscogsClient()`,
    `get_slskd_client()`, `SpotifyWebClient(db)`), quindi un cleanup automatico a
    livello di modulo (atexit) non calzerebbe — non c'e' un'istanza di lunga vita
    da richiudere allo shutdown. Questo mixin da' invece al chiamante gli
    strumenti per chiudere la singola istanza quando ha finito: `close()`
    esplicito e supporto `with client:` per i casi in cui l'uso e' scoped a un
    blocco. Il wiring nei chiamanti (router/services) e' fuori dallo scope di
    questo refactor.
    """

    http: httpx.Client

    def close(self) -> None:
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
