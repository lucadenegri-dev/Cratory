import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import Base  # noqa: E402

CAMELOT_KEYS = [
    "1A", "2A", "3A", "4A", "5A", "6A", "7A", "8A", "9A", "10A", "11A", "12A",
    "1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B",
]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seed_tracks(db):
    """Factory fixture: seed_tracks(n, with_metadata) → inserisce tracce Spotify sintetiche."""
    from app.models import Track

    def _seed(n: int = 30, with_metadata: bool = True):
        for i in range(n):
            db.add(Track(
                platform="spotify",
                spotify_id=f"spot{i:06d}",
                platform_track_id=f"spot{i:06d}",
                source_type="spotify",
                isrc=f"USABC{i:07d}",
                title=f"Track {i}" if with_metadata else None,
                artist=f"Artist {i % 5}" if with_metadata else None,
                year=None,
                duration_seconds=300 + (i % 60),
                bpm=128.0 + (i % 8),
                tonality=f"{(i % 12) + 1}A",
                camelot_key=CAMELOT_KEYS[i % len(CAMELOT_KEYS)],
                status="ready_for_set",
                play_count=i % 10,
            ))
        db.commit()

    return _seed
