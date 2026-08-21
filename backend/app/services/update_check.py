"""Esiste una versione più recente di quella in esecuzione?

Tre esiti, e devono restare tre: aggiornato, disponibile, non verificabile.
Il terzo non può mai degradare nel primo — dire "sei aggiornato" a chi non ha
potuto controllare niente è il modo in cui questa funzione fallisce peggio.
"""
from __future__ import annotations

import logging

import httpx

from app.core.version import app_version, is_newer, parse_version

log = logging.getLogger(__name__)

# Costante, non configurazione: cambiarla è un cambio di codice.
GITHUB_REPO = "lucadenegri-dev/Cratory"
_TIMEOUT_S = 10.0


class UpdateCheckFailed(Exception):
    """Non è stato possibile stabilire se ci sono aggiornamenti."""


class NoReleasePublished(UpdateCheckFailed):
    """GitHub ha risposto 404. Ambiguo per costruzione: o il repository non è
    raggiungibile, o è pubblico ma non ha ancora nessuna release. Non si
    distinguono dalla risposta, e nessuna delle due autorizza a dire che si è
    aggiornati."""


def check(client: httpx.Client | None = None) -> dict:
    corrente = app_version()
    proprio = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        res = client.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        log.info("controllo aggiornamenti fallito: %s", exc)
        raise UpdateCheckFailed(str(exc)) from exc
    finally:
        if proprio:
            client.close()

    if res.status_code == 404:
        raise NoReleasePublished("nessuna release pubblicata, o repository non raggiungibile")
    if res.status_code != 200:
        raise UpdateCheckFailed(f"HTTP {res.status_code}")

    try:
        corpo = res.json()
    except ValueError as exc:
        raise UpdateCheckFailed("risposta non leggibile") from exc

    tag = str(corpo.get("tag_name") or "")
    numeri = parse_version(tag)
    return {
        "current": corrente,
        # Il tag porta la `v`, la versione dell'app no: si normalizza qui, una
        # volta, invece di lasciare che ogni chiamante se ne ricordi.
        "latest": ".".join(str(n) for n in numeri) if numeri else None,
        "update_available": is_newer(tag, corrente),
        "url": corpo.get("html_url"),
        "notes": corpo.get("body") or None,
    }
