import httpx
import pytest

from app.integrations._http import get_with_retries


class _Boom(Exception):
    pass


def test_get_with_retries_raises_after_transport_errors():
    class FailingClient:
        def get(self, url, params=None):
            raise httpx.ConnectError("boom")

    with pytest.raises(_Boom):
        get_with_retries(FailingClient(), "http://x", error_cls=_Boom, retries=1, backoff=0)


def test_get_with_retries_returns_response_on_success():
    resp = httpx.Response(200, text="ok")

    class OkClient:
        def get(self, url, params=None):
            return resp

    assert get_with_retries(OkClient(), "http://x", error_cls=_Boom).status_code == 200
