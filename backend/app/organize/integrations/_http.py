"""Helper HTTP condiviso dai provider esterni: retry sugli errori di trasporto."""

import logging
import ssl
import time

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = 2
DEFAULT_BACKOFF = 0.6


def tls12_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def get_with_retries(client, url, *, error_cls, params=None,
                     retries=DEFAULT_RETRIES, backoff=DEFAULT_BACKOFF):
    return _request_with_retries(
        lambda: client.get(url, params=params), "GET", url,
        error_cls=error_cls, retries=retries, backoff=backoff)


def post_with_retries(client, url, *, error_cls, data=None,
                      retries=DEFAULT_RETRIES, backoff=DEFAULT_BACKOFF):
    return _request_with_retries(
        lambda: client.post(url, data=data), "POST", url,
        error_cls=error_cls, retries=retries, backoff=backoff)


def _request_with_retries(send, method, url, *, error_cls, retries, backoff):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return send()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise error_cls(f"connessione fallita dopo {retries + 1} tentativi ({last_exc})")
