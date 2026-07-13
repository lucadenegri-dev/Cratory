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

    def delete(self, url, params=None):
        self.calls.append(("DELETE", url, params))
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


def test_transfer_state_prefers_most_recent_match_on_duplicate_filename():
    # Senza cancellazione (remove=false) un vecchio tentativo con lo stesso
    # filename puo' restare nello storico: il match deve preferire l'ultimo
    # (quello del transfer appena accodato), non il primo trovato.
    routes = {"/transfers/downloads/bob": {
        "directories": [{"files": [
            {"filename": "Bob\\x.flac", "state": "Cancelled", "id": "old-1"},
            {"filename": "Bob\\x.flac", "state": "InProgress", "id": "new-1"},
        ]}]
    }}
    c = SlskdClient(url="http://h", api_key="k", http=_FakeHttp(routes))
    st = c.transfer_state("bob", "Bob\\x.flac")
    assert st["id"] == "new-1"


def test_transfer_state_filters_by_per_file_username_when_present():
    # Se il payload espone anche lo username per-file, va rispettato: non
    # basta il filename per identificare il transfer giusto.
    routes = {"/transfers/downloads/bob": {
        "directories": [{"files": [
            {"filename": "Bob\\x.flac", "state": "InProgress", "id": "other-user-1",
             "username": "someoneelse"},
            {"filename": "Bob\\x.flac", "state": "InProgress", "id": "bob-1",
             "username": "bob"},
        ]}]
    }}
    c = SlskdClient(url="http://h", api_key="k", http=_FakeHttp(routes))
    st = c.transfer_state("bob", "Bob\\x.flac")
    assert st["id"] == "bob-1"


def test_cancel_download_issues_delete_with_remove_false_by_default():
    http = _FakeHttp({"/transfers/downloads/bob/tid-1": {}})
    c = SlskdClient(url="http://h", api_key="k", http=http)
    c.cancel_download("bob", "tid-1")
    delete = next(call for call in http.calls if call[0] == "DELETE")
    assert delete[1].endswith("/transfers/downloads/bob/tid-1")
    assert delete[2] == {"remove": False}


def test_cancel_download_can_request_remove():
    http = _FakeHttp({"/transfers/downloads/bob/tid-1": {}})
    c = SlskdClient(url="http://h", api_key="k", http=http)
    c.cancel_download("bob", "tid-1", remove=True)
    delete = next(call for call in http.calls if call[0] == "DELETE")
    assert delete[2] == {"remove": True}


def test_classify_transfer_state():
    assert classify_transfer_state("Completed, Succeeded") == "completed"
    assert classify_transfer_state("Completed, Errored") == "failed"
    assert classify_transfer_state("Cancelled") == "failed"
    assert classify_transfer_state("InProgress") == "in_progress"
    assert classify_transfer_state("") == "in_progress"
