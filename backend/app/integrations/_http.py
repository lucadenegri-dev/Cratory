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
