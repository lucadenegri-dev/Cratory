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
    # F2: _fresh_db semina anche le ScanRoot canoniche (id 1/2), quindi la
    # tabella non è più a riga singola: filtra sulla radice appena creata.
    got = db.query(ScanRoot).filter_by(path="/music").one()
    assert got.path == "/music" and got.label == "Main"
