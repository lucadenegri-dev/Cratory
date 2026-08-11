from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import ScanRoot


def test_get_settings_defaults(db):
    with TestClient(app) as client:
        body = client.get("/api/organize/settings").json()
        assert body["naming_template"] == "{artist} - {title}"
        assert body["folder_template"] == "{genre}/{artist}"
        # F2: _fresh_db semina le due ScanRoot canoniche (id 1/2), quindi "nessuna
        # radice configurata" non è più uno stato raggiungibile nei test — verifica
        # che siano esattamente quelle, non un elenco vuoto.
        assert [r["path"] for r in body["roots"]] == ["/inbox", "/library"]


def test_update_settings(db):
    with TestClient(app) as client:
        resp = client.put("/api/organize/settings", json={"folder_template": "{genre}"})
        assert resp.status_code == 200 and resp.json()["folder_template"] == "{genre}"


def test_set_root_target(db):
    # id 3: 1 e 2 sono le ScanRoot canoniche seminate da _fresh_db (F2).
    db.add(ScanRoot(id=3, path="/lib"))
    db.commit()
    with TestClient(app) as client:
        ok = client.put("/api/organize/settings/roots/3/target", json={"target_root": "/lib/Library"})
        assert ok.status_code == 200
        roots = client.get("/api/organize/settings").json()["roots"]
        target = next(r for r in roots if r["id"] == 3)
        assert target["target_root"] == "/lib/Library"


def test_set_target_non_absolute_rejected(db):
    db.add(ScanRoot(id=3, path="/lib"))
    db.commit()
    with TestClient(app) as client:
        assert client.put("/api/organize/settings/roots/3/target",
                          json={"target_root": "relativo"}).status_code == 400
