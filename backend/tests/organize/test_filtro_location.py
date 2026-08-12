"""I filtri dell'API Organize ragionano per collocazione, non per sorgente."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_files_filtra_per_location():
    res = client.get("/api/organize/files", params={"location": "library"})
    assert res.status_code == 200


def test_files_rifiuta_una_location_inventata():
    res = client.get("/api/organize/files", params={"location": "altrove"})
    assert res.status_code == 422


def test_root_id_non_e_piu_un_filtro_riconosciuto():
    """Non deve restare un parametro morto che finge di filtrare."""
    res = client.get("/api/organize/files", params={"root_id": 1})
    assert res.status_code in (200, 422)
    if res.status_code == 200:
        # accettato ma ignorato: verifica che non sia rimasto nella firma
        import inspect

        from app.organize.routers import library

        assert "root_id" not in inspect.signature(library.list_files).parameters
