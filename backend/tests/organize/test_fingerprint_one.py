from app.organize.integrations.acoustid import AcoustIDError
from app.organize.services.fingerprint import fingerprint_one
from tests.organize.conftest import make_audio_file


class FakeClient:
    def __init__(self, candidates=None, error=False):
        self.candidates = candidates or []
        self.error = error

    def identify(self, path):
        if self.error:
            raise AcoustIDError("boom")
        return self.candidates


def test_sets_mbid_when_above_threshold():
    f = make_audio_file(1)
    client = FakeClient([{"mbid": "mb-1", "score": 0.9}])
    assert fingerprint_one(f, client) == "mb-1"
    assert f.mbid == "mb-1"


def test_none_when_below_threshold():
    f = make_audio_file(2)
    client = FakeClient([{"mbid": "mb-2", "score": 0.2}])
    assert fingerprint_one(f, client) is None
    assert f.mbid is None


def test_none_and_no_raise_on_error():
    f = make_audio_file(3)
    client = FakeClient(error=True)
    assert fingerprint_one(f, client) is None
    assert f.mbid is None
