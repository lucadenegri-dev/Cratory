from sqlalchemy import inspect

from app.db import engine


def test_undo_journal_table():
    cols = {c["name"] for c in inspect(engine).get_columns("undo_journal")}
    assert {"run_id", "op_seq", "kind", "file_id", "from_path", "to_path",
            "prior_tags_json", "quarantine_path", "reversed"} <= cols
