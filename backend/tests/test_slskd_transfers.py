# backend/tests/test_slskd_transfers.py
from app.integrations.slskd import SlskdClient, SlskdFile, classify_transfer_state


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text, self.content = payload, status, "", b"x"

    def json(self):
        return self._p


class _FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _match(self, url):
        for frag, payload in self.routes.items():
            if frag in url:
                return payload
        return {}

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return _Resp(self._match(url))

    def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        return _Resp(self._match(url))


def _file():
    return SlskdFile(username="bob", filename="Bob\\x.flac", size=10, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)


def test_enqueue_posts_file_list():
    http = _FakeHttp({"/transfers/downloads/bob": {}})
    c = SlskdClient(url="http://h", api_key="k", http=http)
    c.enqueue_download(_file())
    post = http.calls[0]
    assert post[0] == "POST"
    assert post[1].endswith("/transfers/downloads/bob")
    assert post[2] == [{"filename": "Bob\\x.flac", "size": 10}]


def test_transfer_state_finds_file():
    routes = {"/transfers/downloads/bob": {
        "directories": [{"files": [{"filename": "Bob\\x.flac", "state": "Completed, Succeeded"}]}]
    }}
    c = SlskdClient(url="http://h", api_key="k", http=_FakeHttp(routes))
    st = c.transfer_state("bob", "Bob\\x.flac")
    assert st["state"] == "Completed, Succeeded"


def test_classify_transfer_state():
    assert classify_transfer_state("Completed, Succeeded") == "completed"
    assert classify_transfer_state("Completed, Errored") == "failed"
    assert classify_transfer_state("Cancelled") == "failed"
    assert classify_transfer_state("InProgress") == "in_progress"
    assert classify_transfer_state("") == "in_progress"
