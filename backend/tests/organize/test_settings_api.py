from fastapi.testclient import TestClient

from app.main import app


def test_get_settings_defaults(db):
    with TestClient(app) as client:
        body = client.get("/api/organize/settings").json()
        assert body["naming_template"] == "{artist} - {title}"
        assert body["folder_template"] == "{genre}/{artist}"


def test_update_settings(db):
    with TestClient(app) as client:
        resp = client.put("/api/organize/settings", json={"folder_template": "{genre}"})
        assert resp.status_code == 200 and resp.json()["folder_template"] == "{genre}"
