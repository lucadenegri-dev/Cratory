from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import ScanRoot


def test_get_settings_defaults(db):
    with TestClient(app) as client:
        body = client.get("/api/organize/settings").json()
        assert body["naming_template"] == "{artist} - {title}"
        assert body["folder_template"] == "{genre}/{artist}"
        # "Nessuna radice configurata" non è raggiungibile nei test: conftest.
        # SEEDED_SCAN_ROOT_IDS semina 1/2. Confronto su insieme, non sull'ordine
        # (la query non garantisce un ORDER BY).
        assert {r["path"] for r in body["roots"]} == {"/inbox", "/library"}


def test_update_settings(db):
    with TestClient(app) as client:
        resp = client.put("/api/organize/settings", json={"folder_template": "{genre}"})
        assert resp.status_code == 200 and resp.json()["folder_template"] == "{genre}"


def test_set_root_target(db):
    # ScanRoot id >= 3: 1 e 2 sono le canoniche (conftest.SEEDED_SCAN_ROOT_IDS).
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
