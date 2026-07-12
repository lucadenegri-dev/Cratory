"""Client per il daemon Soulseek headless slskd (REST API v0).

slskd fa la rete P2P (login, peer, code); Cratory orchestra. Usato SOLO come
downloader: non si sfrutta la condivisione. Confermare gli endpoint contro
lo Swagger del proprio slskd (<SLSKD_URL>/swagger).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.integrations._http import ClosableHttpClient, get_with_retries, raise_for_status

BASE = "/api/v0"


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
        self.url = (url if url is not None else settings.slskd_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.slskd_api_key
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
        if r.status_code >= 400:
            raise SlskdError(f"slskd {r.status_code}: {r.text[:160]}")
        return r.json() if r.content else {}

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
        """
        text = f"{artist} {title}".strip()
        if not text:
            return []
        created = self._post("/searches", json={
            "searchText": text,
            "searchTimeout": search_timeout_ms,
            "responseLimit": response_limit,
        })
        search_id = created.get("id")
        if not search_id:
            raise SlskdError("slskd: ricerca senza id.")
        waited = 0.0
        while waited < max_wait:
            state = self._get(f"/searches/{search_id}")
            if state.get("isComplete") or "completed" in str(state.get("state", "")).lower():
                break
            time.sleep(poll_interval)
            waited += poll_interval
        responses = self._get(f"/searches/{search_id}/responses")
        return self._flatten_responses(responses)

    def enqueue_download(self, file: "SlskdFile") -> None:
        self._post(f"/transfers/downloads/{file.username}",
                   json=[{"filename": file.filename, "size": file.size or 0}])

    def transfer_state(self, username: str, filename: str) -> dict | None:
        data = self._get(f"/transfers/downloads/{username}")
        for directory in data.get("directories") or []:
            for f in directory.get("files") or []:
                if f.get("filename") == filename:
                    return f
        return None

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
    return bool(settings.slskd_url and settings.slskd_download_dir)


def get_slskd_client() -> SlskdClient:
    if not settings.slskd_url:
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
