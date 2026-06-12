"""Modelli SQLAlchemy. Rekordbox e' la fonte primaria dei dati DJ (BPM, key, beatgrid, cue)."""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    rekordbox_track_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    spotify_id: Mapped[str | None] = mapped_column(String, index=True)
    soundcloud_id: Mapped[str | None] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String, index=True)  # spotify | soundcloud | local
    title: Mapped[str | None] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String, index=True)
    album: Mapped[str | None] = mapped_column(String)
    genre: Mapped[str | None] = mapped_column(String, index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    bpm: Mapped[float | None] = mapped_column(Float, index=True)
    tonality: Mapped[str | None] = mapped_column(String, index=True)  # Camelot, es. "7A"
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    date_added: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    beatgrid_points: Mapped[list["BeatgridPoint"]] = relationship(
        back_populates="track", cascade="all, delete-orphan"
    )
    cue_points: Mapped[list["CuePoint"]] = relationship(
        back_populates="track", cascade="all, delete-orphan"
    )


class BeatgridPoint(Base):
    __tablename__ = "beatgrid_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    start_seconds: Mapped[float] = mapped_column(Float)
    bpm: Mapped[float] = mapped_column(Float)
    meter: Mapped[str | None] = mapped_column(String)
    beat: Mapped[int | None] = mapped_column(Integer)

    track: Mapped[Track] = relationship(back_populates="beatgrid_points")


class CuePoint(Base):
    __tablename__ = "cue_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    name: Mapped[str | None] = mapped_column(String)
    type: Mapped[str | None] = mapped_column(String)
    start_seconds: Mapped[float] = mapped_column(Float)
    num: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)

    track: Mapped[Track] = relationship(back_populates="cue_points")


class ImportReport(Base):
    __tablename__ = "import_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str | None] = mapped_column(String)
    stats: Mapped[dict] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setlist(Base):
    __tablename__ = "setlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    target_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    start_bpm: Mapped[float | None] = mapped_column(Float)
    end_bpm: Mapped[float | None] = mapped_column(Float)
    strategy: Mapped[str | None] = mapped_column(String)
    prompt: Mapped[str | None] = mapped_column(Text)
    global_explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tracks: Mapped[list["SetlistTrack"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan", order_by="SetlistTrack.position"
    )


class SetlistTrack(Base):
    __tablename__ = "setlist_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    transition_score: Mapped[float | None] = mapped_column(Float)
    transition_reason: Mapped[str | None] = mapped_column(Text)
    ai_reason: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String)  # low | medium | high
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    setlist: Mapped[Setlist] = relationship(back_populates="tracks")
    track: Mapped[Track] = relationship()
