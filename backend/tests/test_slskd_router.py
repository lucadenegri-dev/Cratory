"""Router /api/slskd: stato connessione Soulseek + connetti/disconnetti.

Il client slskd e' sempre mockato (nessuna rete). `settings.slskd_url` viene
monkeypatchato per pilotare il ramo "configurato / non configurato".
"""
from fastapi.testclient import TestClient

from app.core.config import settings
from app.integrations.slskd import SlskdError
from app.main import app
from app.routers import slskd as slskd_router

CONNECTED = {"state": "Connected, LoggedIn", "isConnected": True, "isLoggedIn": True,
             "isConnecting": False, "isTransitioning": False}
DISCONNECTED = {"state": "Disconnected", "isConnected": False, "isLoggedIn": False,
                "isConnecting": False, "isTransitioning": False}


class _FakeClient:
    def __init__(self, state=None, username="lucadenegri", raise_state=False):
        self._state = state if state is not None else CONNECTED
        self._username = username
        self._raise_state = raise_state
        self.connect_called = False
        self.disconnect_called = False

    def server_state(self):
        if isinstance(self._raise_state, Exception):
            raise self._raise_state
        if self._raise_state:
            raise SlskdError("daemon irraggiungibile")
        return self._state

    def soulseek_username(self):
        return self._username

    def connect(self):
        self.connect_called = True

    def disconnect(self):
        self.disconnect_called = True

    def close(self):
        pass


def _use_client(monkeypatch, fake, *, url="http://localhost:5030"):
    monkeypatch.setattr(settings, "slskd_url", url)
    monkeypatch.setattr(slskd_router, "get_slskd_client", lambda: fake)


def test_status_not_configured_returns_configured_false(monkeypatch):
    monkeypatch.setattr(settings, "slskd_url", "")
    r = TestClient(app).get("/api/slskd/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["is_connected"] is False
    # Non configurato -> nessun URL da linkare.
    assert body["web_url"] is None


def test_status_returns_connection_state(monkeypatch):
    _use_client(monkeypatch, _FakeClient(state=CONNECTED))
    r = TestClient(app).get("/api/slskd/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["is_connected"] is True
    assert body["is_logged_in"] is True
    assert body["username"] == "lucadenegri"
    assert body["web_url"] == "http://localhost:5030"


def test_status_unreachable_daemon_returns_reachable_false(monkeypatch):
    _use_client(monkeypatch, _FakeClient(raise_state=True))
    r = TestClient(app).get("/api/slskd/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["reachable"] is False
    assert body["is_connected"] is False
    # web_url c'e' anche col demone giu': e' proprio quando serve il link manuale.
    assert body["web_url"] == "http://localhost:5030"


def test_status_web_url_strips_trailing_slash(monkeypatch):
    _use_client(monkeypatch, _FakeClient(state=CONNECTED), url="http://localhost:5030/")
    body = TestClient(app).get("/api/slskd/status").json()
    assert body["web_url"] == "http://localhost:5030"


def test_connect_calls_client_and_returns_status(monkeypatch):
    fake = _FakeClient(state=CONNECTED)
    _use_client(monkeypatch, fake)
    r = TestClient(app).post("/api/slskd/connect")
    assert r.status_code == 200
    assert fake.connect_called is True
    assert r.json()["is_connected"] is True


def test_disconnect_calls_client(monkeypatch):
    fake = _FakeClient(state=DISCONNECTED)
    _use_client(monkeypatch, fake)
    r = TestClient(app).post("/api/slskd/disconnect")
    assert r.status_code == 200
    assert fake.disconnect_called is True


def test_connect_not_configured_returns_409(monkeypatch):
    monkeypatch.setattr(settings, "slskd_url", "")
    r = TestClient(app).post("/api/slskd/connect")
    assert r.status_code == 409


def _errore(status: int) -> SlskdError:
    """Un errore come lo costruisce `raise_for_status`: il codice HTTP ci
    arriva attaccato all'eccezione, non nel tipo."""
    exc = SlskdError(f"slskd {status}: ")
    exc.status_code = status
    return exc


def test_status_401_dice_che_la_chiave_e_rifiutata(monkeypatch):
    """Un 401 non e' "il demone e' giu'": e' acceso, e sta rifiutando noi.
    Senza distinguerli la UI vede un demone raggiungibile (`/health` risponde
    a chiunque) e uno stato che dice "irraggiungibile", e l'unica cosa che
    puo' offrire e' "Connetti" — che ridara' 401 all'infinito."""
    _use_client(monkeypatch, _FakeClient(raise_state=_errore(401)))
    body = TestClient(app).get("/api/slskd/status").json()
    assert body["unauthorized"] is True
    assert body["reachable"] is False


def test_status_403_e_lo_stesso_problema(monkeypatch):
    """Chiave valida ma con ruolo o CIDR insufficienti: rifiutati uguale, e la
    riparazione (riscrivere la nostra voce) e' la stessa."""
    _use_client(monkeypatch, _FakeClient(raise_state=_errore(403)))
    assert TestClient(app).get("/api/slskd/status").json()["unauthorized"] is True


def test_status_demone_giu_non_e_un_problema_di_chiave(monkeypatch):
    """Il contro-caso, o `unauthorized` potrebbe essere sempre vero e passare
    lo stesso: connessione rifiutata, nessuno status code."""
    _use_client(monkeypatch, _FakeClient(raise_state=True))
    body = TestClient(app).get("/api/slskd/status").json()
    assert body["reachable"] is False
    assert body["unauthorized"] is False
