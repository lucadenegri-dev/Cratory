"""Dove il callback OAuth riporta l'utente (app/routers/spotify.py).

Il difetto che questi test fissano: il callback rimandava SEMPRE alla prima
origine di `FRONTEND_ORIGIN` (`http://localhost:3000`), che nel bundle desktop
non esiste — la pagina sta su `tauri://localhost` e il backend su
`127.0.0.1:8000`. Lo scambio del token riusciva, poi il webview restava su una
navigazione fallita: dal lato dell'utente il bottone "Accetta" di Spotify
semplicemente non andava avanti.

La destinazione ora la chiede la pagina (`/login?return_to=...`), viene
validata contro le origini che questa installazione riconosce (le stesse del
CORS: accettarla com'e' farebbe di /callback un redirect aperto) e viaggia
insieme allo state anti-CSRF.
"""
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.routers import spotify as spotify_router

WEBVIEW = "tauri://localhost"


@pytest.fixture()
def client(monkeypatch):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    monkeypatch.setattr(spotify_router.settings, "frontend_origin", "http://localhost:3000")
    # Nessuna rete: lo scambio del token e' l'unica cosa che uscirebbe.
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _pulisci_stati():
    spotify_router._pending_states.clear()
    yield
    spotify_router._pending_states.clear()


def _login(client, **params):
    """/login segue il redirect verso Spotify se lo si lascia fare: qui serve
    solo lo state emesso, che si legge dal Location."""
    r = client.get("/api/spotify/login", params=params, follow_redirects=False)
    assert r.status_code in (302, 307), r.status_code
    return parse_qs(urlsplit(r.headers["location"]).query)["state"][0]


def _callback(client, **params):
    return client.get("/api/spotify/callback", params=params, follow_redirects=False)


@pytest.fixture(autouse=True)
def _credenziali(monkeypatch):
    """`/login` costruisce l'authorize URL: senza client id solleva
    SpotifyNotConfigured e nessuno di questi test arriverebbe al callback."""
    monkeypatch.setattr(spotify_router.runtime_settings, "spotify_client_id",
                        lambda: "id-di-prova")
    monkeypatch.setattr(spotify_router.runtime_settings, "spotify_client_secret",
                        lambda: "segreto-di-prova")


# --- la destinazione chiesta dalla pagina viene onorata -----------------------


def test_torna_dove_ha_chiesto_la_pagina(client):
    state = _login(client, return_to="http://localhost:3000/setup")

    r = _callback(client, code="authcode", state=state)

    assert r.headers["location"].startswith("http://localhost:3000/setup?")
    assert "spotify=connected" in r.headers["location"]


def test_senza_return_to_resta_il_comportamento_di_sempre(client):
    state = _login(client)

    r = _callback(client, code="authcode", state=state)

    assert r.headers["location"].startswith("http://localhost:3000/settings?")


def test_anche_l_errore_torna_dove_ha_chiesto_la_pagina(client):
    """Il caso peggiore e' proprio questo: un errore che atterra su un'origine
    morta lascia l'utente su una pagina bianca, senza sapere cos'e' successo."""
    state = _login(client, return_to="http://localhost:3000/setup")

    r = _callback(client, error="access_denied", state=state)

    assert r.headers["location"].startswith("http://localhost:3000/setup?")
    assert "spotify=error" in r.headers["location"]


# --- niente redirect aperto ---------------------------------------------------


def test_origine_estranea_ignorata(client):
    """`return_to` arriva dalla query string. Un'origine che questa
    installazione non riconosce non deve diventare la destinazione: si
    ripiega sul default, non si redirige fuori."""
    state = _login(client, return_to="https://evil.example/rubami-il-codice")

    r = _callback(client, code="authcode", state=state)

    assert "evil.example" not in r.headers["location"]
    assert r.headers["location"].startswith("http://localhost:3000/settings?")


def test_return_to_non_e_un_url_ignorato(client):
    state = _login(client, return_to="/setup")  # relativo: nessuna origine

    r = _callback(client, code="authcode", state=state)

    assert r.headers["location"].startswith("http://localhost:3000/settings?")


def test_query_del_return_to_scartata(client):
    """La query la scrive il callback (spotify=connected|error): quella che
    arriva dalla pagina non deve sopravvivere e confondere il parsing."""
    state = _login(client, return_to="http://localhost:3000/setup?spotify=connected")

    r = _callback(client, error="access_denied", state=state)

    query = parse_qs(urlsplit(r.headers["location"]).query)
    assert query["spotify"] == ["error"]


# --- il guscio desktop: origine non-http, quindi pagina di ritorno ------------


def test_webview_torna_nell_app_con_una_pagina_non_con_un_location(client):
    """`tauri://localhost` e' sempre ammessa (come nel CORS): e' il modo in cui
    il bundle parla con se stesso. Un 302 verso uno schema custom e' terreno
    incerto per WKWebView, quindi la si serve una paginetta che fa il salto e
    che, se il salto non avviene, resta comunque leggibile."""
    state = _login(client, return_to=f"{WEBVIEW}/setup")

    r = _callback(client, code="authcode", state=state)

    assert r.status_code == 200
    assert "location" not in {k.lower() for k in r.headers}
    assert f"{WEBVIEW}/setup?spotify=connected" in r.text


def test_la_pagina_di_ritorno_non_e_una_pagina_vuota(client):
    """Se il salto automatico non parte, l'utente e' dentro una finestra senza
    barra degli indirizzi: deve trovarci un link, non il nulla."""
    state = _login(client, return_to=f"{WEBVIEW}/settings")

    r = _callback(client, code="authcode", state=state)

    assert "<a " in r.text
    assert "Cratory" in r.text


def test_la_pagina_di_ritorno_non_annuncia_un_successo_che_non_c_e_stato(client):
    """La si vede solo quando il salto automatico non parte — cioe' proprio
    quando quella frase resta li' a farsi leggere."""
    state = _login(client, return_to=f"{WEBVIEW}/setup")

    r = _callback(client, error="access_denied", state=state)

    assert "connected" not in r.text.lower()
    assert "collegato" not in r.text.lower()
    assert "failed" in r.text.lower() or "non riuscito" in r.text.lower()


# --- la destinazione viaggia con lo state, e ne condivide il ciclo di vita ----


def test_state_scaduto_riporta_comunque_dentro_l_app(client):
    """Uno state scaduto e' un login da rifare, non una ragione per abbandonare
    l'utente fuori: la destinazione era gia' stata validata all'emissione."""
    state = _login(client, return_to=f"{WEBVIEW}/setup")
    scaduto = spotify_router._pending_states[state]
    spotify_router._pending_states[state] = scaduto._replace(
        issued=scaduto.issued - spotify_router._STATE_TTL_SECONDS - 1
    )

    r = _callback(client, code="authcode", state=state)

    assert f"{WEBVIEW}/setup" in r.text
    assert "detail=invalid_state" in r.text


def test_state_sconosciuto_non_conosce_nessuna_destinazione(client):
    """Senza state valido non c'e' nessun `return_to` ricordato: default, e
    soprattutto nessun modo per un terzo di scegliere la destinazione."""
    r = _callback(client, code="authcode", state="mai-emesso")

    assert r.headers["location"].startswith("http://localhost:3000/settings?")
    assert "detail=invalid_state" in r.headers["location"]
