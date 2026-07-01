from fastapi.testclient import TestClient

from app.main import app
from app.models import ScanRoot


def test_get_settings_defaults(db):
    with TestClient(app) as client:
        body = client.get("/api/settings").json()
        assert body["naming_template"] == "{artist} - {title}"
        assert body["folder_template"] == "{genre}/{artist}"
        assert body["roots"] == []


def test_update_settings(db):
    with TestClient(app) as client:
        resp = client.put("/api/settings", json={"folder_template": "{genre}"})
        assert resp.status_code == 200 and resp.json()["folder_template"] == "{genre}"


def test_set_root_target(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.commit()
    with TestClient(app) as client:
        ok = client.put("/api/settings/roots/1/target", json={"target_root": "/lib/Library"})
        assert ok.status_code == 200
        roots = client.get("/api/settings").json()["roots"]
        assert roots[0]["target_root"] == "/lib/Library"


def test_set_target_non_absolute_rejected(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.commit()
    with TestClient(app) as client:
        assert client.put("/api/settings/roots/1/target",
                          json={"target_root": "relativo"}).status_code == 400


def test_settings_cratory_base_url_roundtrip(db):
    with TestClient(app) as client:
        assert client.get("/api/settings").json()["cratory_base_url"] is None
        r = client.put("/api/settings", json={"cratory_base_url": "http://localhost:8000"})
        assert r.status_code == 200
        assert r.json()["cratory_base_url"] == "http://localhost:8000"
        # gli altri campi non vengono toccati
        assert r.json()["naming_template"] == "{artist} - {title}"
        # stringa vuota = bridge disattivato (torna NULL)
        r2 = client.put("/api/settings", json={"cratory_base_url": "  "})
        assert r2.json()["cratory_base_url"] is None
        # PUT senza il campo = non toccare
        client.put("/api/settings", json={"cratory_base_url": "http://localhost:8000"})
        r3 = client.put("/api/settings", json={"folder_template": "{genre}"})
        assert r3.json()["cratory_base_url"] == "http://localhost:8000"
