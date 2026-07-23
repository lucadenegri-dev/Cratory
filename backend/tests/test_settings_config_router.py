"""Router /api/settings/config + /share-library.

`get_db` è sovrascritto con la fixture `db` (in-memory) per non toccare il DB reale;
`runtime_settings` è ricaricato su quel DB a ogni test.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import config, runtime_settings as rs
from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    # StaticPool: una sola connessione in-memory condivisa tra il thread del test e
    # il threadpool di TestClient (stesso motivo di test_settings_router.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    # default .env hermetici (le tracce reali di backend/.env non devono influire)
    for k in ("library_root", "archive_root", "slskd_download_dir", "slskd_url"):
        monkeypatch.setattr(config.settings, k, "")
    app.dependency_overrides[get_db] = lambda: session
    rs.load(session)
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_get_config_shape(client):
    body = client.get("/api/settings/config").json()
    for k in ("library_root", "archive_root", "slskd_download_dir", "slskd_url",
              "slskd_config_path"):
        assert k in body and "value" in body[k] and "source" in body[k]
    assert body["share_library"] is False
    assert body["library_root"]["source"] == "env"


def test_patch_override_url_persists(client):
    r = client.patch("/api/settings/config", json={"slskd_url": "http://box:9999"})
    assert r.status_code == 200
    body = r.json()
    assert body["slskd_url"]["value"] == "http://box:9999"
    assert body["slskd_url"]["source"] == "db"
    assert client.get("/api/settings/config").json()["slskd_url"]["value"] == "http://box:9999"


def test_patch_dir_valid(client, tmp_path):
    r = client.patch("/api/settings/config", json={"slskd_download_dir": str(tmp_path)})
    assert r.status_code == 200
    assert r.json()["slskd_download_dir"]["value"] == str(tmp_path)


def test_patch_invalid_path_is_422(client):
    r = client.patch("/api/settings/config", json={"library_root": "/nope/does/not/exist"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_setting"


def test_patch_invalid_url_is_422(client):
    r = client.patch("/api/settings/config", json={"slskd_url": "not-a-url"})
    assert r.status_code == 422


def test_patch_empty_clears_override(client):
    client.patch("/api/settings/config", json={"slskd_url": "http://box:9999"})
    r = client.patch("/api/settings/config", json={"slskd_url": ""})
    assert r.json()["slskd_url"]["source"] == "env"
    assert r.json()["slskd_url"]["value"] == ""


def test_share_library_enable(client, tmp_path, monkeypatch):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: x\n")
    cfg.chmod(0o600)
    lib = tmp_path / "Library"
    lib.mkdir()
    monkeypatch.setattr(rs, "slskd_config_path", lambda: str(cfg))
    monkeypatch.setattr(rs, "library_root", lambda: str(lib))
    monkeypatch.setattr(rs, "slskd_url", lambda: "")  # niente rescan

    r = client.put("/api/settings/share-library", json={"enabled": True})
    assert r.status_code == 200
    body = r.json()
    assert body["share_library"] is True
    assert body["applied_to_yaml"] is True
    assert body["rescan"] is False
    from ruamel.yaml import YAML
    data = YAML().load(cfg.read_text())
    assert str(lib) in data["shares"]["directories"]


def test_share_library_enable_without_library_is_409(client, tmp_path, monkeypatch):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: x\n")
    monkeypatch.setattr(rs, "slskd_config_path", lambda: str(cfg))
    monkeypatch.setattr(rs, "library_root", lambda: "")
    r = client.put("/api/settings/share-library", json={"enabled": True})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "share_precondition"
