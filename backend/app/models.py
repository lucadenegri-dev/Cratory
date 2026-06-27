"""Modelli SQLAlchemy del chunk 1: radici di scan e file audio."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScanRoot(Base):
    __tablename__ = "scan_root"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime)

    files: Mapped[list["AudioFile"]] = relationship(
        back_populates="root", cascade="all, delete-orphan"
    )


class AudioFile(Base):
    __tablename__ = "audio_file"
    __table_args__ = (UniqueConstraint("root_id", "path", name="uq_audio_root_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(ForeignKey("scan_root.id"), index=True)
    path: Mapped[str] = mapped_column(String, index=True)
    ext: Mapped[str] = mapped_column(String)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String, index=True)
    hash_method: Mapped[str] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    album: Mapped[str | None] = mapped_column(String)
    album_artist: Mapped[str | None] = mapped_column(String)
    genre: Mapped[str | None] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String)
    track_no: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    has_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="present", index=True)
    scan_error: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    root: Mapped["ScanRoot"] = relationship(back_populates="files")
