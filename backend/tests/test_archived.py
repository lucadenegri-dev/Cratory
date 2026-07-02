"""Stato 'scartata': Track.archived e setting ARCHIVE_ROOT."""
import pytest

from app.core.config import Settings
from app.models import Track


def test_archived_default_false(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert t.archived is False


def test_archive_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.archive_root == ""
