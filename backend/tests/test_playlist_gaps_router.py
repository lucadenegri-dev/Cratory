"""GET /api/playlists/library/gaps non deve essere catturato da /{playlist_id}/gaps (fix A6)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
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


def test_library_gaps_not_shadowed_by_playlist_route(client):
    r = client.get("/api/playlists/library/gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "library"
