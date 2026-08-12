"""I filtri dell'API Organize ragionano per collocazione, non per sorgente."""

from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile

client = TestClient(app)


def _seed(db):
    # Stesso root_id per entrambe: se il filtro leggesse ancora root_id invece
    # di location (schema morto, F3b), le due query darebbero lo stesso esito.
    db.add(AudioFile(id=1, root_id=1, path="/m/in.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     location="inbox"))
    db.add(AudioFile(id=2, root_id=1, path="/m/lib.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     location="library"))
    db.commit()


def test_files_filtra_per_location(db):
    _seed(db)
    res = client.get("/api/organize/files", params={"location": "library"})
    assert res.status_code == 200
    assert [r["id"] for r in res.json()] == [2]

    res = client.get("/api/organize/files", params={"location": "inbox"})
    assert res.status_code == 200
    assert [r["id"] for r in res.json()] == [1]


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
