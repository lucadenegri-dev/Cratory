"""Il flag che decide se il primo avvio porta al wizard."""
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.db import Base, get_db
from app.main import app

client = TestClient(app)


def setup_test_db():
    """Crea un database di test in memoria con tutte le tabelle."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_di_default_il_wizard_non_e_completato():
    db = setup_test_db()
    try:
        app.dependency_overrides[get_db] = lambda: db
        assert client.get("/api/setup/state").json() == {"completed": False}
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_completamento_persistito():
    db = setup_test_db()
    try:
        app.dependency_overrides[get_db] = lambda: db
        assert client.put("/api/setup/state", json={"completed": True}).json() == {"completed": True}
        assert client.get("/api/setup/state").json() == {"completed": True}
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_si_puo_riaprire():
    """Riaprire il wizard da Impostazioni non deve essere un vicolo cieco."""
    db = setup_test_db()
    try:
        app.dependency_overrides[get_db] = lambda: db
        client.put("/api/setup/state", json={"completed": True})
        client.put("/api/setup/state", json={"completed": False})
        assert client.get("/api/setup/state").json() == {"completed": False}
    finally:
        app.dependency_overrides.clear()
        db.close()
