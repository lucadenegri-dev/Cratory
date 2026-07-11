"""Engine, sessione e creazione schema. Niente Alembic: app locale."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_schema(eng=None) -> None:
    """create_all + ALTER per colonne aggiunte dopo (niente Alembic: app locale)."""
    import app.models  # noqa: F401

    eng = eng or engine
    Base.metadata.create_all(eng)
    from sqlalchemy import inspect, text

    inspector = inspect(eng)
    if "scan_root" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("scan_root")}
        if "target_root" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE scan_root ADD COLUMN target_root VARCHAR"))
    if "settings" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("settings")}
        if "language" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE settings ADD COLUMN language VARCHAR DEFAULT 'en'"))
    if "audio_file" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("audio_file")}
        if "isrc" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN isrc VARCHAR"))
        if "mbid" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN mbid VARCHAR"))
        with eng.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audio_file_mbid ON audio_file (mbid)"
            ))


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
