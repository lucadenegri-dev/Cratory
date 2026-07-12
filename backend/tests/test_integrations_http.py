"""Test dell'helper HTTP condiviso dai provider esterni (E11): la mappatura
status->errore e il parsing JSON centralizzati in `app.integrations._http`,
usati da lastfm/discogs/slskd/spotify. Nessuna rete: solo `httpx.Response`
finte, stesso stile dei test dei singoli client.
"""

import pytest

from app.integrations._http import ClosableHttpClient, get_json, parse_json, raise_for_status


class _FakeResp:
    def __init__(self, payload=None, status=200, text=""):
        self._payload, self.status_code, self.text = payload, status, text

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


class BoomError(Exception):
    pass


# ---- raise_for_status --------------------------------------------------


def test_raise_for_status_no_op_sotto_400():
    raise_for_status(_FakeResp(status=200), BoomError, name="X")  # non solleva


def test_raise_for_status_429_con_messaggio_dedicato():
    with pytest.raises(BoomError, match="rate limit custom"):
        raise_for_status(_FakeResp(status=429), BoomError, name="X",
                          rate_limit_message="rate limit custom")


def test_raise_for_status_429_senza_messaggio_dedicato_cade_nel_ramo_generico():
    """slskd non ha mai distinto 429: senza `rate_limit_message` il 429 sollevà
    comunque, ma col formato generico "{name} {status}: {testo}"."""
    with pytest.raises(BoomError, match=r"^X 429: boom$"):
        raise_for_status(_FakeResp(status=429, text="boom"), BoomError, name="X")


def test_raise_for_status_generico_status_e_testo_troncato():
    with pytest.raises(BoomError, match=r"^X 500: 01234$"):
        raise_for_status(_FakeResp(status=500, text="0123456789"), BoomError,
                          name="X", text_preview=5)


def test_raise_for_status_context_inserito_tra_status_e_testo():
    with pytest.raises(BoomError, match=r"^X 404 su /foo: nope$"):
        raise_for_status(_FakeResp(status=404, text="nope"), BoomError,
                          name="X", context=" su /foo")


# ---- parse_json ----------------------------------------------------------


def test_parse_json_ok():
    assert parse_json(_FakeResp({"a": 1}), BoomError, message="bad") == {"a": 1}


def test_parse_json_wrappa_il_valueerror():
    with pytest.raises(BoomError, match="bad json"):
        parse_json(_FakeResp(None), BoomError, message="bad json")


# ---- get_json (compone get_with_retries + raise_for_status + parse_json) --


class _FakeHttp:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self.resp


def test_get_json_successo():
    http = _FakeHttp(_FakeResp({"ok": True}))
    out = get_json(http, "http://x/y", error_cls=BoomError, name="X", params={"q": 1})
    assert out == {"ok": True}
    assert http.calls == [("http://x/y", {"q": 1})]


def test_get_json_errore_status_propaga_error_cls():
    http = _FakeHttp(_FakeResp(status=500, text="fail"))
    with pytest.raises(BoomError, match=r"X 500: fail"):
        get_json(http, "http://x/y", error_cls=BoomError, name="X")


def test_get_json_rate_limit_message():
    http = _FakeHttp(_FakeResp(status=429))
    with pytest.raises(BoomError, match="troppe richieste"):
        get_json(http, "http://x/y", error_cls=BoomError, name="X",
                 rate_limit_message="troppe richieste")


# ---- ClosableHttpClient ----------------------------------------------------


class _FakeHttpxClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _DummyClient(ClosableHttpClient):
    def __init__(self):
        self.http = _FakeHttpxClient()


def test_close_delega_al_client_httpx():
    c = _DummyClient()
    c.close()
    assert c.http.closed is True


def test_context_manager_chiude_in_uscita():
    c = _DummyClient()
    with c as ctx:
        assert ctx is c
        assert c.http.closed is False
    assert c.http.closed is True
