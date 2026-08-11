from sqlalchemy import inspect

from app.db import engine
from app.organize.models import ScanRoot


def test_schema_has_expected_tables_and_columns():
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"scan_root", "audio_file"} <= tables
    cols = {c["name"] for c in insp.get_columns("audio_file")}
    assert {"content_hash", "hash_method", "scan_error", "status"} <= cols


def test_scan_root_roundtrip(db):
    db.add(ScanRoot(path="/music", label="Main"))
    db.commit()
    got = db.query(ScanRoot).one()
    assert got.path == "/music" and got.label == "Main"
