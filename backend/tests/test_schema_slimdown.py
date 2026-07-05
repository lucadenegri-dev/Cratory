# backend/tests/test_schema_slimdown.py
from sqlalchemy import create_engine, inspect, text

from app.db import Base, ensure_schema
import app.models  # noqa: F401

_DEAD = {"mood", "danceability", "vocalness", "genre_secondary", "genre_source",
         "album_id", "enrichment_source", "enrichment_confidence", "enriched_at", "mbid"}


def test_dead_columns_absent_on_fresh_db():
    eng = create_engine("sqlite:///:memory:")
    ensure_schema(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("tracks")}
    assert _DEAD.isdisjoint(cols)
    assert "energy" in cols and "bpm" in cols and "camelot_key" in cols
    assert "enrichment_cache" not in inspect(eng).get_table_names()


def test_rebuild_drops_dead_columns_on_legacy_db():
    eng = create_engine("sqlite:///:memory:")
    # DB "vecchio" con colonna morta e dati in una colonna sopravvissuta
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE tracks (id INTEGER PRIMARY KEY, "
                          "source_type VARCHAR, energy INTEGER, mood VARCHAR, genre VARCHAR)"))
        conn.execute(text("INSERT INTO tracks (id, source_type, energy, mood, genre) "
                          "VALUES (1, 'spotify', 80, 'dark', 'Techno')"))
    ensure_schema(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("tracks")}
    assert "mood" not in cols and "energy" in cols
    with eng.begin() as conn:
        row = conn.execute(text("SELECT energy, genre FROM tracks WHERE id=1")).one()
    assert row[0] == 80 and row[1] == "Techno"
