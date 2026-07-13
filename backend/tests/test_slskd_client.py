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

    def delete(self, url, params=None):
        self.calls.append(("DELETE", url, params))
        return _Resp(self._match(url))


def test_search_aggregates_files_from_responses():
    routes = {
        "/searches/abc/responses": [
            {
                "username": "bob",
                "hasFreeUploadSlot": True,
                "queueLength": 0,
                "uploadSpeed": 1_500_000,
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
    # La ricerca e' gia' completa (isComplete True): legge le risposte e aggrega.
    files = c.search("Daft Punk", "Da Funk", max_wait=5.0, poll_interval=0.0)
    assert len(files) == 1
    f = files[0]
    assert isinstance(f, SlskdFile)
    assert f.username == "bob"
    assert f.extension == "flac"
    assert f.has_free_slot is True
    assert f.upload_speed == 1_500_000
    # ha interrogato lo stato della ricerca prima di leggere le risposte
    assert any(call[0] == "GET" and call[1].endswith("/searches/abc") for call in http.calls)
    # la POST di creazione ricerca include il searchText e i parametri per-ricerca
    post = next(call for call in http.calls if call[0] == "POST")
    assert post[2]["searchText"] == "Daft Punk Da Funk"
    assert post[2]["responseLimit"] > 0
    assert post[2]["searchTimeout"] > 0


def test_search_deletes_the_search_after_harvesting_responses():
    # Le ricerche si accumulano nel daemon se non si ripuliscono: dopo aver
    # letto le risposte, la ricerca va cancellata (best-effort).
    routes = {
        "/searches/abc/responses": [],
        "/searches/abc": {"isComplete": True, "state": "Completed"},
        "/searches": {"id": "abc"},
    }
    http = _FakeHttp(routes)
    c = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    c.search("Daft Punk", "Da Funk", max_wait=5.0, poll_interval=0.0)
    deletes = [call for call in http.calls if call[0] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0][1].endswith("/searches/abc")


def test_search_delete_failure_is_best_effort():
    # Se la cancellazione della ricerca fallisce, la search() non deve
    # propagare l'errore: i risultati vanno restituiti comunque.
    class _FailingDeleteHttp(_FakeHttp):
        def delete(self, url, params=None):
            self.calls.append(("DELETE", url, params))
            return _Resp({}, status=500)

    routes = {
        "/searches/abc/responses": [
            {"username": "bob", "hasFreeUploadSlot": True, "queueLength": 0,
             "files": [{"filename": "Bob\\x.flac", "size": 1, "bitRate": None, "length": None}]},
        ],
        "/searches/abc": {"isComplete": True, "state": "Completed"},
        "/searches": {"id": "abc"},
    }
    http = _FailingDeleteHttp(routes)
    c = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    files = c.search("Daft Punk", "Da Funk", max_wait=5.0, poll_interval=0.0)
    assert len(files) == 1  # nessuna eccezione propagata dal DELETE fallito


def test_search_exits_early_when_responses_stabilize(monkeypatch):
    # responseCount cresce poi si stabilizza per due poll consecutivi: la
    # search() non deve attendere fino al tetto max_wait (isComplete resta
    # sempre False: senza early-exit macinerebbe tutti i poll fino al tetto).
    import app.integrations.slskd as slskd_mod
    monkeypatch.setattr(slskd_mod.time, "sleep", lambda s: None)

    class _StabilizingHttp(_FakeHttp):
        def __init__(self, routes):
            super().__init__(routes)
            self.state_calls = 0

        def get(self, url, params=None):
            self.calls.append(("GET", url, params))
            if url.endswith("/searches/abc"):
                self.state_calls += 1
                counts = [0, 3, 3, 3, 3, 3, 3, 3]
                idx = min(self.state_calls - 1, len(counts) - 1)
                return _Resp({"isComplete": False, "responseCount": counts[idx]})
            return _Resp(self._match(url))

    routes = {"/searches/abc/responses": [], "/searches": {"id": "abc"}}
    http = _StabilizingHttp(routes)
    c = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    c.search("Daft Punk", "Da Funk", max_wait=100.0, poll_interval=0.5)
    # senza early-exit avrebbe interrogato lo stato molte piu' volte (max_wait/poll_interval = 200)
    assert http.state_calls <= 4
