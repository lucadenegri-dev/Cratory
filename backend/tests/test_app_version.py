"""La versione ha una fonte sola. Il file nella radice, con l'ambiente che lo
scavalca: in un bundle Tauri quella radice non esiste."""
from fastapi.testclient import TestClient

from app.core import version as v
from app.main import app


def test_legge_il_file_della_radice(monkeypatch):
    monkeypatch.delenv(v.VERSION_ENV, raising=False)
    assert v.app_version() == "0.9.0"


def test_l_ambiente_scavalca_il_file(monkeypatch):
    """È il seam per il packager: nel bundle il numero arriva da fuori."""
    monkeypatch.setenv(v.VERSION_ENV, "1.2.3")
    assert v.app_version() == "1.2.3"


def test_ambiente_vuoto_non_conta(monkeypatch):
    monkeypatch.setenv(v.VERSION_ENV, "   ")
    assert v.app_version() == "0.9.0"


def test_senza_file_ne_ambiente_non_esplode(monkeypatch, tmp_path):
    """Un checkout incompleto deve poter avviare l'app: la versione è
    un'informazione, non una precondizione."""
    monkeypatch.delenv(v.VERSION_ENV, raising=False)
    monkeypatch.setattr(v, "_percorso_version", lambda: tmp_path / "manca")
    assert v.app_version() == "0.0.0-dev"


def test_endpoint(monkeypatch):
    monkeypatch.delenv(v.VERSION_ENV, raising=False)
    assert TestClient(app).get("/api/version").json() == {"version": "0.9.0"}


def test_package_json_non_diverge():
    """Due numeri che raccontano cose diverse sono peggio di un numero solo."""
    import json
    from pathlib import Path
    radice = Path(__file__).resolve().parent.parent.parent
    pkg = json.loads((radice / "frontend" / "package.json").read_text())
    assert pkg["version"] == (radice / "VERSION").read_text().strip()
