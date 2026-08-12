"""Le rotte Organize vivono sotto /api/organize; le omonime di Cratory restano
al loro posto (nessuna collisione silenziosa)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _paths() -> set[str]:
    # NB: non usiamo {r.path for r in app.routes}: sulla versione di FastAPI
    # installata in questo venv (0.141.1, ammessa da requirements.txt
    # "fastapi>=0.115,<1.0"), app.routes contiene oggetti _IncludedRouter
    # (lazy wrapper introdotti per gli include_router) privi di .path.
    # app.openapi()["paths"] resta l'API pubblica stabile per l'elenco
    # effettivo dei path HTTP registrati, indipendente da questo dettaglio
    # interno di versione.
    return set(app.openapi()["paths"].keys())


def test_rotte_organize_prefissate():
    paths = _paths()
    assert "/api/organize/issues" in paths
    assert "/api/organize/settings" in paths
    assert "/api/organize/plan" in paths
    assert "/api/organize/duplicates" in paths


def test_nessuna_rotta_organize_fuori_dal_prefisso():
    paths = _paths()
    assert "/api/issues" not in paths
    assert "/api/duplicates" not in paths
    assert "/api/plan" not in paths


def test_rotte_cratory_intatte():
    paths = _paths()
    # "/api/settings" nudo non e' mai stato un path registrato: il router
    # Cratory (app/routers/settings.py) ha prefix="/api/settings" ma nessuna
    # rotta sulla suffix vuota, solo /language, /config, /share-library.
    # "/api/settings/language" e' la rotta Cratory reale ed e' anche il punto
    # di collisione vero descritto dal brief: prima del prefisso, anche il
    # router Organize esponeva /language sotto lo stesso prefix "/api/settings".
    assert "/api/settings/language" in paths
    assert "/api/tracks" in paths
    assert "/api/library/index" in paths


def test_endpoint_organize_risponde():
    res = client.get("/api/organize/issues")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
