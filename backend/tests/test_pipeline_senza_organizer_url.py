"""La pipeline non punta più a un'app esterna: Organize è una sezione."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    # Stesso pattern di test_pipeline_router: senza dependency_overrides la
    # route userebbe l'engine di modulo, dove le tabelle esistono solo se un
    # altro test le ha create prima — verde o rosso a seconda dell'ordine.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_settings_non_ha_piu_organizer_url():
    from app.core.config import settings

    assert not hasattr(settings, "organizer_url")


def test_la_risposta_pipeline_non_espone_organizer_url(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")

    res = client.get("/api/pipeline")
    assert res.status_code == 200
    assert "organizer_url" not in res.json()


def test_lo_schema_non_dichiara_piu_il_campo():
    from app.schemas import PipelineOut

    assert "organizer_url" not in PipelineOut.model_fields
