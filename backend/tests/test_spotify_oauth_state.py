"""Anti-CSRF sull'OAuth Spotify (app/routers/spotify.py): il callback deve
rifiutare uno `state` mancante o non combaciante con quello emesso da /login,
e consumarlo one-shot (un replay dello stesso state valido deve fallire).
Nessuna rete: SpotifyWebClient.exchange_code e' monkeypatchato."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.routers import spotify as spotify_router


@pytest.fixture()
def client(monkeypatch):
    # get_db isolato: il callback non lo tocca finche' lo state non e' valido, ma
    # resta piu' sicuro non dipendere mai dal DB reale dello sviluppatore.
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
    # Singola origine pulita: il default reale ("http://localhost:3000,http://
    # localhost:3001", vedi test_callback_redirect_rotto_con_piu_origini sotto)
    # produce un Location header non parsabile come URL, non correlato a cio' che
    # questi test verificano (lo state anti-CSRF).
    monkeypatch.setattr(spotify_router.settings, "frontend_origin", "http://localhost:3000")
    yield TestClient(app)
    app.dependency_overrides.clear()


def _get_callback(client, **params):
    # follow_redirects=False va passato per-richiesta: a costruzione del TestClient
    # non e' onorato in questa combinazione starlette/httpx (la richiesta seguirebbe
    # il redirect e tenterebbe di fare il parsing dell'URL, con RemoteProtocolError
    # se e' malformato — vedi il bug documentato in fondo al file).
    return client.get("/api/spotify/callback", params=params, follow_redirects=False)


@pytest.fixture(autouse=True)
def _clean_pending_states():
    """_pending_states e' un dict globale di modulo (app locale mono-utente): va
    isolato tra i test per non far combaciare per caso lo state di un test
    precedente."""
    spotify_router._pending_states.clear()
    yield
    spotify_router._pending_states.clear()


def _location(resp) -> str:
    return resp.headers["location"]


# --- state mancante o non combaciante: rifiutato -------------------------------


def test_callback_senza_state_rifiutato(client, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: called.update(n=called["n"] + 1))

    r = _get_callback(client, code="authcode")

    assert r.status_code in (302, 307)
    assert "detail=invalid_state" in _location(r)
    assert called["n"] == 0  # nessuno scambio token senza state valido


def test_callback_state_sconosciuto_rifiutato(client, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: called.update(n=called["n"] + 1))

    r = _get_callback(client, code="authcode", state="mai-emesso")

    assert "detail=invalid_state" in _location(r)
    assert called["n"] == 0


def test_callback_state_di_unaltra_sessione_rifiutato(client, monkeypatch):
    """Un solo state pendente ('quello giusto'): un valore diverso (anche se ben
    formato) non deve passare — verifica che il confronto sia sul valore, non solo
    sulla presenza di QUALCHE state pendente."""
    spotify_router._remember_state("stato-legittimo")
    called = {"n": 0}
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: called.update(n=called["n"] + 1))

    r = _get_callback(client, code="authcode", state="stato-falso")

    assert "detail=invalid_state" in _location(r)
    assert called["n"] == 0
    # lo state legittimo NON e' stato consumato dal tentativo con lo state sbagliato
    assert "stato-legittimo" in spotify_router._pending_states


# --- state valido: passa e viene consumato one-shot ----------------------------


def test_callback_state_valido_passa(client, monkeypatch):
    spotify_router._remember_state("stato-valido")
    called = {"n": 0}
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: called.update(n=called["n"] + 1))

    r = _get_callback(client, code="authcode", state="stato-valido")

    assert "spotify=connected" in _location(r)
    assert called["n"] == 1


def test_callback_state_e_one_shot_replay_rifiutato(client, monkeypatch):
    spotify_router._remember_state("stato-riusato")
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code", lambda self, code: None)

    first = _get_callback(client, code="authcode", state="stato-riusato")
    assert "spotify=connected" in _location(first)

    called = {"n": 0}
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: called.update(n=called["n"] + 1))
    second = _get_callback(client, code="authcode", state="stato-riusato")

    assert "detail=invalid_state" in _location(second)
    assert called["n"] == 0  # il replay non ha innescato un secondo scambio token


def test_callback_state_scaduto_rifiutato(client, monkeypatch):
    """Uno state emesso oltre STATE_TTL fa fallire il callback (login abbandonato).

    NB: non si monkeypatcha time.monotonic globalmente — TestClient gira su un
    event loop asyncio/anyio che usa lo stesso orologio per i suoi timeout interni,
    quindi congelarlo bloccherebbe la richiesta invece di limitarsi a farla fallire.
    Si retrodata direttamente il timestamp memorizzato per quello state."""
    spotify_router._remember_state("stato-vecchio")
    pendente = spotify_router._pending_states["stato-vecchio"]
    spotify_router._pending_states["stato-vecchio"] = pendente._replace(
        issued=pendente.issued - spotify_router._STATE_TTL_SECONDS - 1
    )
    called = {"n": 0}
    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code",
                        lambda self, code: called.update(n=called["n"] + 1))

    r = _get_callback(client, code="authcode", state="stato-vecchio")

    assert "detail=invalid_state" in _location(r)
    assert called["n"] == 0


# --- errori dell'exchange non bypassano comunque il check dello state ---------


def test_callback_token_exchange_fallito_dopo_state_valido(client, monkeypatch):
    from app.integrations.spotify import SpotifyError

    spotify_router._remember_state("stato-ok-ma-exchange-rotto")

    def _raise(self, code):
        raise SpotifyError("boom")

    monkeypatch.setattr(spotify_router.SpotifyWebClient, "exchange_code", _raise)

    r = _get_callback(client, code="authcode", state="stato-ok-ma-exchange-rotto")

    assert "detail=token_exchange" in _location(r)


# FRONTEND_ORIGIN e' una lista CSV di origini (CORS in app/main.py, default
# multi-origine in config.py): il callback deve redirigere alla PRIMA origine,
# non all'intera lista (la virgola dentro l'host rende il Location invalido —
# httpx solleva RemoteProtocolError seguendolo). Bug scovato da questi test
# (xfail strict) e corretto in routers/spotify.py il 2026-07-12.
def test_callback_redirect_url_valido_con_piu_origini_frontend(client, monkeypatch):
    from urllib.parse import urlsplit

    monkeypatch.setattr(spotify_router.settings, "frontend_origin",
                        "http://localhost:3000,http://localhost:3001")

    r = _get_callback(client, code="authcode")  # nessuno state -> redirect di errore

    location = _location(r)
    assert "," not in location, "virgola dell'elenco origini finita nel Location header"
    parsed = urlsplit(location)
    assert parsed.scheme and parsed.netloc, f"Location header non e' un URL valido: {location!r}"
