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
import time

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = 2      # tentativi aggiuntivi oltre al primo (3 in totale)
DEFAULT_BACKOFF = 0.6    # secondi, crescente: 0.6s, 1.2s, ...


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
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return client.get(url, params=params)
        except httpx.HTTPError as exc:  # SSL / connessione / lettura / timeout
            last_exc = exc
            if attempt < retries:
                wait = backoff * (attempt + 1)
                logger.warning(
                    "GET %s fallita (tentativo %d/%d): %s — riprovo tra %.1fs",
                    url, attempt + 1, retries + 1, exc, wait,
                )
                time.sleep(wait)
    raise error_cls(f"connessione fallita dopo {retries + 1} tentativi ({last_exc})")
