from sqlalchemy import inspect

from app.db import engine
from app.models import DupGroup, DupMember, Issue


def test_chunk2_tables_exist():
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"issue", "dup_group", "dup_member"} <= tables


def test_issue_columns():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("issue")}
    assert {"file_id", "type", "field", "severity", "suggested_fix_json", "status"} <= cols


def test_dup_group_columns():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("dup_group")}
    assert {"match_kind", "keeper_file_id", "keeper_overridden", "dismissed", "signature"} <= cols
