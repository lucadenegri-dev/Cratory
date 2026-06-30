from app.integrations.slskd import SlskdClient, SlskdFile


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text, self.content = payload, status, "", b"x"

    def json(self):
        return self._p


class _FakeHttp:
    """Risponde in base al path; registra le chiamate. Nessuna rete."""

    def __init__(self, routes):
        self.routes = routes  # dict: substring del path -> payload
        self.calls = []

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


def test_search_aggregates_files_from_responses():
    routes = {
        "/searches/abc/responses": [
            {
                "username": "bob",
                "hasFreeUploadSlot": True,
                "queueLength": 0,
                "files": [
                    {"filename": "Bob\\Daft Punk - Da Funk.flac", "size": 40000000,
                     "bitRate": None, "length": 220},
                ],
            }
        ],
        "/searches/abc": {"isComplete": True, "state": "Completed"},
        "/searches": {"id": "abc"},
    }
    http = _FakeHttp(routes)
    c = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    files = c.search("Daft Punk", "Da Funk", wait_seconds=0.0, poll_interval=0.0)
    assert len(files) == 1
    f = files[0]
    assert isinstance(f, SlskdFile)
    assert f.username == "bob"
    assert f.extension == "flac"
    assert f.has_free_slot is True
    # la POST di creazione ricerca include il searchText
    post = next(call for call in http.calls if call[0] == "POST")
    assert post[2] == {"searchText": "Daft Punk Da Funk"}
