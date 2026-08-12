"""Le sorgenti non sono più un'entità esposta dall'API."""

from app.main import app


def _paths() -> set[str]:
    # Vedi tests/organize/test_route_prefix.py: su questa versione di FastAPI
    # (0.141.1) app.routes contiene _IncludedRouter privi di .path, quindi
    # usiamo openapi()["paths"] come elenco stabile dei path HTTP registrati.
    return set(app.openapi()["paths"].keys())


def test_le_rotte_sources_non_esistono_piu():
    paths = _paths()
    assert "/api/organize/sources" not in paths
    assert not any(p.startswith("/api/organize/sources/") for p in paths)


def test_la_rotta_target_per_radice_non_esiste_piu():
    assert "/api/organize/settings/roots/{root_id}/target" not in _paths()


def test_le_altre_rotte_organize_sono_intatte():
    paths = _paths()
    assert "/api/organize/issues" in paths
    assert "/api/organize/plan" in paths
    assert "/api/organize/settings" in paths
