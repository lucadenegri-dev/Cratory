"""Login alla rete Soulseek dal frontend: stato connessione + connetti/disconnetti.

Le credenziali Soulseek NON passano da qui: restano nella config di slskd
(`slskd.yml`/env). Cratory legge solo lo stato della connessione via l'API key
gia' in uso e comanda connect/disconnect sul demone. Vedi `integrations/slskd.py`.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.integrations.slskd import SlskdError, get_slskd_client
from app.services import slskd_daemon

router = APIRouter(prefix="/api/slskd", tags=["slskd"])


class SlskdStatus(BaseModel):
    # configured = SLSKD_URL presente (si sa dove sta il demone); reachable =
    # il demone ha risposto. I flag di connessione valgono solo se reachable.
    configured: bool
    reachable: bool
    is_connected: bool
    is_logged_in: bool
    is_connecting: bool
    is_transitioning: bool
    state: str | None = None
    username: str | None = None
    # URL della web UI di slskd (= SLSKD_URL: il demone serve UI e REST sulla
    # stessa origin). Valorizzato appena `configured`, anche se il demone e' giu':
    # il link serve proprio quando i download da Cratory falliscono. None se non
    # configurato. NB: e' l'URL visto dal backend; nel setup self-hosted (stessa
    # macchina) coincide con quello del browser.
    web_url: str | None = None


_NOT_CONFIGURED = SlskdStatus(
    configured=False, reachable=False, is_connected=False, is_logged_in=False,
    is_connecting=False, is_transitioning=False,
)


def _status() -> SlskdStatus:
    """Interroga il demone. Se SLSKD_URL manca -> non configurato; se il demone
    non risponde -> configurato ma non raggiungibile (200 con reachable=False,
    cosi' la UI puo' fare polling senza trattare il down come errore duro)."""
    slskd_url = runtime_settings.slskd_url()
    if not slskd_url:
        return _NOT_CONFIGURED
    web_url = slskd_url.rstrip("/")
    client = get_slskd_client()
    try:
        state = client.server_state()
        username = client.soulseek_username()
    except SlskdError:
        return SlskdStatus(
            configured=True, reachable=False, is_connected=False,
            is_logged_in=False, is_connecting=False, is_transitioning=False,
            web_url=web_url,
        )
    finally:
        client.close()
    return SlskdStatus(
        configured=True,
        reachable=True,
        web_url=web_url,
        is_connected=bool(state.get("isConnected")),
        is_logged_in=bool(state.get("isLoggedIn")),
        # slskd espone sia isConnecting sia isLoggingIn: per la UI sono la stessa
        # cosa ("transizione in corso, aspetta").
        is_connecting=bool(state.get("isConnecting") or state.get("isLoggingIn")),
        is_transitioning=bool(state.get("isTransitioning")),
        state=state.get("state"),
        username=username,
    )


def _require_configured() -> None:
    if not runtime_settings.slskd_url():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL).")


@router.get("/status", response_model=SlskdStatus)
def slskd_status() -> SlskdStatus:
    return _status()


@router.post("/connect", response_model=SlskdStatus)
def slskd_connect() -> SlskdStatus:
    """Connette il demone alla rete Soulseek (login con le credenziali gia' in
    slskd) e ritorna lo stato aggiornato."""
    _require_configured()
    client = get_slskd_client()
    try:
        client.connect()
    except SlskdError as exc:
        raise api_error(502, "slskd_error", f"slskd error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()
    return _status()


@router.post("/disconnect", response_model=SlskdStatus)
def slskd_disconnect() -> SlskdStatus:
    """Disconnette il demone dalla rete Soulseek e ritorna lo stato aggiornato."""
    _require_configured()
    client = get_slskd_client()
    try:
        client.disconnect()
    except SlskdError as exc:
        raise api_error(502, "slskd_error", f"slskd error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()
    return _status()


# Endpoint del demone: configurazione, avvio e arresto.


class DaemonStatus(BaseModel):
    reachable: bool
    owned: bool | None
    pid: int | None = None


class DaemonConfig(BaseModel):
    username: str
    password: str
    # None = campo omesso dalla richiesta: write_config lascia intatto quel
    # che c'e' gia' nel file (i default si applicano solo al primo setup,
    # quando il file non esiste ancora). Niente default qui: risolverli in
    # questo modello li renderebbe indistinguibili da un valore scelto
    # davvero dal chiamante, e li farebbe riscrivere ad ogni giro.
    port: int | None = None
    download_dir: str | None = None


class DaemonConfigResult(BaseModel):
    configured: bool
    username: str


@router.get("/daemon/status", response_model=DaemonStatus)
def daemon_status() -> DaemonStatus:
    return DaemonStatus(**slskd_daemon.daemon_status())


@router.post("/daemon/start", response_model=DaemonStatus)
def daemon_start() -> DaemonStatus:
    try:
        return DaemonStatus(**slskd_daemon.start())
    except slskd_daemon.AlreadyUp as exc:
        raise api_error(409, "slskd_already_up", str(exc)) from exc
    except slskd_daemon.NotInstalled as exc:
        raise api_error(409, "slskd_not_installed", str(exc)) from exc
    except slskd_daemon.StartFailed as exc:
        raise api_error(502, "slskd_start_failed", str(exc), reason=str(exc)) from exc
    except slskd_daemon.UnsupportedPlatform as exc:
        raise api_error(501, "slskd_unsupported_platform", str(exc)) from exc


@router.post("/daemon/stop", response_model=DaemonStatus)
def daemon_stop() -> DaemonStatus:
    try:
        return DaemonStatus(**slskd_daemon.stop())
    except slskd_daemon.NotOurs as exc:
        raise api_error(409, "slskd_not_ours", str(exc)) from exc
    except slskd_daemon.UnsupportedPlatform as exc:
        raise api_error(501, "slskd_unsupported_platform", str(exc)) from exc


@router.put("/daemon/config", response_model=DaemonConfigResult)
def daemon_config(req: DaemonConfig) -> DaemonConfigResult:
    """La password entra e non esce: non ne teniamo copia e non la
    rispondiamo. L'username sì, si rilegge dal file."""
    config = slskd_daemon.default_config_path()
    slskd_daemon.write_config(
        config, username=req.username, password=req.password,
        port=req.port, download_dir=req.download_dir,
    )
    return DaemonConfigResult(configured=True, username=req.username)
