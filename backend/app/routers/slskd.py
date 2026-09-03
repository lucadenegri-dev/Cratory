"""Login alla rete Soulseek dal frontend: stato connessione + connetti/disconnetti.

Le credenziali Soulseek NON passano da qui: restano nella config di slskd
(`slskd.yml`/env). Cratory legge solo lo stato della connessione via l'API key
gia' in uso e comanda connect/disconnect sul demone. Vedi `integrations/slskd.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.slskd import SlskdError, get_slskd_client
from app.services import binary_installer, slskd_daemon

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
    # Il demone ha risposto, ma ha rifiutato la nostra chiave API (401/403).
    # E' un caso a parte da "non raggiungibile", e non lo si puo' dedurre dal
    # resto: `/health` e' anonimo, quindi il demone risulta acceso lo stesso e
    # l'unica azione offerta sarebbe "Connetti", che ridarebbe 401 all'infinito.
    # Chi lo legge (la riga di Impostazioni) offre invece la riparazione.
    unauthorized: bool = False
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
    except SlskdError as exc:
        # `reachable` resta False: un demone che ci rifiuta non e' utilizzabile,
        # ed e' la stessa lettura che ne da' `slskd_unreachable` (401/403 =
        # infrastruttura, non colpa della singola traccia). Il perche' lo dice
        # `unauthorized`. Lo status code arriva attaccato all'eccezione da
        # `_http.raise_for_status`; un errore di trasporto non ce l'ha.
        codice = getattr(exc, "status_code", None)
        return SlskdStatus(
            configured=True, reachable=False, is_connected=False,
            is_logged_in=False, is_connecting=False, is_transitioning=False,
            web_url=web_url, unauthorized=codice in (401, 403),
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
    # A che punto è il percorso, non solo se il demone risponde: la riga che
    # configura slskd sceglie da qui l'unica azione sensata (scaricare,
    # configurare, avviare, collegare). Additivi: nessun campo esistente
    # cambia significato.
    installed: bool = False
    configured: bool = False
    username: str | None = None


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


def _con_percorso(base: dict) -> DaemonStatus:
    """Completa la risposta del servizio con i tre campi di percorso.

    Passa di qui ognuna delle tre risposte -- status, start e stop -- perché
    tutte e tre costruiscono lo STESSO modello da dict diversi: lasciare che i
    campi nuovi cadano sui loro default farebbe rispondere `installed: false`
    subito dopo un avvio riuscito, e la UI tornerebbe a offrire il download di
    un binario che ha appena eseguito.

    La password non entra: `read_username` legge l'utente e basta.
    """
    percorso_config = slskd_daemon.default_config_path()
    configurato = percorso_config.is_file()
    return DaemonStatus(
        **base,
        installed=binary_installer.installed_path("slskd") is not None,
        configured=configurato,
        username=slskd_daemon.read_username(percorso_config) if configurato else None,
    )


@router.get("/daemon/status", response_model=DaemonStatus)
def daemon_status() -> DaemonStatus:
    return _con_percorso(slskd_daemon.daemon_status())


@router.post("/daemon/start", response_model=DaemonStatus)
def daemon_start() -> DaemonStatus:
    try:
        return _con_percorso(slskd_daemon.start())
    except slskd_daemon.AlreadyUp as exc:
        raise api_error(409, "slskd_already_up", str(exc)) from exc
    except slskd_daemon.AlreadyOwned as exc:
        raise api_error(409, "slskd_already_owned", str(exc)) from exc
    except slskd_daemon.NotInstalled as exc:
        raise api_error(409, "slskd_not_installed", str(exc)) from exc
    except slskd_daemon.StartFailed as exc:
        raise api_error(502, "slskd_start_failed", str(exc), reason=str(exc)) from exc
    except slskd_daemon.UnsupportedPlatform as exc:
        raise api_error(501, "slskd_unsupported_platform", str(exc)) from exc


@router.post("/daemon/stop", response_model=DaemonStatus)
def daemon_stop() -> DaemonStatus:
    try:
        return _con_percorso(slskd_daemon.stop())
    except slskd_daemon.NotOurs as exc:
        raise api_error(409, "slskd_not_ours", str(exc)) from exc
    except slskd_daemon.UnsupportedPlatform as exc:
        raise api_error(501, "slskd_unsupported_platform", str(exc)) from exc


@router.put("/daemon/config", response_model=DaemonConfigResult)
def daemon_config(req: DaemonConfig, db: Session = Depends(get_db)) -> DaemonConfigResult:
    """La password entra e non esce: non ne teniamo copia e non la
    rispondiamo. L'username sì, si rilegge dal file.

    Nessun controllo di piattaforma qui (a differenza di start/stop): questo
    endpoint scrive solo un file YAML, un'operazione che su Windows funziona
    esattamente come altrove — la piattaforma conta solo per gestire il
    processo del demone.
    """
    config = slskd_daemon.default_config_path()
    scritto = slskd_daemon.write_config(
        config, username=req.username, password=req.password,
        port=req.port, download_dir=req.download_dir,
    )
    # Config nata da zero: porta e cartella scelte (magari solo di default)
    # vanno scritte anche nelle impostazioni di Cratory, altrimenti
    # `slskd_url()` resta vuoto e `is_reachable()`/`start()` non sapranno mai
    # a quale URL bussare, anche a demone avviato con successo.
    if scritto.created:
        runtime_settings.apply(db, "slskd_url", f"http://127.0.0.1:{scritto.port}")
        runtime_settings.apply(db, "slskd_download_dir", scritto.download_dir)
    # La chiave API invece NON segue `created`: quella scritta qui e' sempre e
    # solo quella che sta nel file (`_assicura_chiave_api` riusa quella gia'
    # presente), quindi riallinearla non sovrascrive nessuna scelta
    # dell'utente — mentre non farlo lascia Cratory a firmare le richieste con
    # la chiave sbagliata, che e' il 401 da cui si e' partiti.
    runtime_settings.apply(db, "slskd_api_key", scritto.api_key)
    return DaemonConfigResult(configured=True, username=req.username)


class ApiKeyRepair(BaseModel):
    """Esito della riparazione dell'autenticazione. `needs_restart` non e' il
    negato di `restarted` per caso: sono due cose diverse per chi legge —
    "l'ho riavviato io" e "tocca a te", e la seconda va detta, o l'utente
    resta col 401 convinto di aver finito."""
    configured: bool
    restarted: bool
    needs_restart: bool


@router.post("/daemon/api-key", response_model=ApiKeyRepair)
def daemon_api_key(db: Session = Depends(get_db)) -> ApiKeyRepair:
    """Ripara l'autenticazione verso il demone: scrive in slskd.yml la chiave
    API di Cratory (se non c'e' gia'), la specchia nelle impostazioni e
    riavvia il demone perche' la legga.

    Serve a chi ha configurato slskd prima che il percorso guidato scrivesse
    una chiave: il suo demone e' acceso, funzionante, e risponde 401 a noi —
    e la fase "configura", che rimetterebbe le cose a posto, non gli viene
    piu' offerta (si vede solo a demone spento). A differenza della password
    Soulseek, la chiave non richiede di ridomandare niente all'utente.

    Il riavvio riguarda solo il demone nostro: la regola del modulo non cambia
    qui. Per gli altri `needs_restart` dice che il passo manca ancora, perche'
    slskd le `api_keys` le legge una volta sola, all'avvio.
    """
    try:
        chiave = slskd_daemon.ensure_api_key(slskd_daemon.default_config_path())
    except slskd_daemon.ConfigMissing as exc:
        raise api_error(409, "slskd_not_configured", str(exc)) from exc
    runtime_settings.apply(db, "slskd_api_key", chiave)

    try:
        nostro = slskd_daemon.owned_pid() is not None
    except slskd_daemon.UnsupportedPlatform:
        # Scrivere un file YAML su Windows funziona come altrove: negare tutto
        # con un 501 butterebbe via anche la meta' che si e' appena fatta.
        nostro = False
    if not nostro:
        return ApiKeyRepair(configured=True, restarted=False, needs_restart=True)

    try:
        slskd_daemon.stop()
        slskd_daemon.start()
    except slskd_daemon.NotOurs:
        # Morto da solo fra il controllo e lo stop: la chiave c'e', il riavvio
        # no. Non e' un errore da 502, e' un passo che resta all'utente.
        return ApiKeyRepair(configured=True, restarted=False, needs_restart=True)
    except slskd_daemon.DaemonError as exc:
        raise api_error(502, "slskd_start_failed", str(exc), reason=str(exc)) from exc
    return ApiKeyRepair(configured=True, restarted=True, needs_restart=False)
