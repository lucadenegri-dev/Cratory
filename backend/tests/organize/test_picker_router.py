"""Router /api/picker: il servizio native_picker è sempre monkeypatchato."""
from fastapi.testclient import TestClient

from app.main import app
from app.organize.services import native_picker

client = TestClient(app)


def test_availability_riflette_il_servizio(monkeypatch):
    monkeypatch.setattr(native_picker, "picker_available", lambda: True)
    assert client.get("/api/organize/picker/availability").json() == {"available": True}
    monkeypatch.setattr(native_picker, "picker_available", lambda: False)
    assert client.get("/api/organize/picker/availability").json() == {"available": False}


def test_pick_ritorna_il_percorso(monkeypatch):
    seen: dict = {}

    def fake_pick(kind, start=None, prompt=None):
        seen.update(kind=kind, start=start, prompt=prompt)
        return "/Users/x/Music"

    monkeypatch.setattr(native_picker, "pick_path", fake_pick)
    r = client.post("/api/organize/picker/pick",
                    json={"kind": "folder", "start": "/Users/x", "prompt": "Libreria"})
    assert r.status_code == 200
    assert r.json() == {"path": "/Users/x/Music"}
    assert seen == {"kind": "folder", "start": "/Users/x", "prompt": "Libreria"}


def test_pick_annullato_ritorna_path_null(monkeypatch):
    monkeypatch.setattr(native_picker, "pick_path", lambda *a, **k: None)
    r = client.post("/api/organize/picker/pick", json={"kind": "file"})
    assert r.status_code == 200
    assert r.json() == {"path": None}


def test_pick_non_disponibile_409(monkeypatch):
    def raise_unavailable(*a, **k):
        raise native_picker.PickerUnavailableError

    monkeypatch.setattr(native_picker, "pick_path", raise_unavailable)
    r = client.post("/api/organize/picker/pick", json={"kind": "folder"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "picker_unavailable"


def test_pick_occupato_409(monkeypatch):
    def raise_busy(*a, **k):
        raise native_picker.PickerBusyError

    monkeypatch.setattr(native_picker, "pick_path", raise_busy)
    r = client.post("/api/organize/picker/pick", json={"kind": "folder"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "picker_busy"


def test_kind_non_valido_422():
    assert client.post("/api/organize/picker/pick", json={"kind": "symlink"}).status_code == 422
