from sqlalchemy import create_engine, inspect, text

from app.db import engine, ensure_schema


def test_chunk3_tables_and_column():
    insp = inspect(engine)
    assert {"settings", "plan", "plan_op"} <= set(insp.get_table_names())
    assert "target_root" in {c["name"] for c in insp.get_columns("scan_root")}


def test_ensure_schema_adds_target_root_to_old_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, "
            "label VARCHAR, last_scanned_at DATETIME)"
        ))
    ensure_schema(eng)
    assert "target_root" in {c["name"] for c in inspect(eng).get_columns("scan_root")}
