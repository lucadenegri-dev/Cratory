"""Modelli SQLAlchemy del chunk 1: radici di scan e file audio."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
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
    target_root: Mapped[str | None] = mapped_column(String)

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


class Issue(Base):
    __tablename__ = "issue"
    __table_args__ = (UniqueConstraint("file_id", "type", "field", name="uq_issue_file_type_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    field: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, index=True)
    detail: Mapped[str] = mapped_column(Text)
    suggested_fix_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DupGroup(Base):
    __tablename__ = "dup_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_kind: Mapped[str] = mapped_column(String)
    keeper_file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"))
    keeper_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    signature: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["DupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class DupMember(Base):
    __tablename__ = "dup_member"
    __table_args__ = (UniqueConstraint("group_id", "file_id", name="uq_dupmember_group_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("dup_group.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    action: Mapped[str] = mapped_column(String)

    group: Mapped["DupGroup"] = relationship(back_populates="members")


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # riga singola, id=1
    naming_template: Mapped[str] = mapped_column(String, default="{artist} - {title}")
    folder_template: Mapped[str] = mapped_column(String, default="{genre}/{artist}")
    dedup_keep_rules_json: Mapped[dict | None] = mapped_column(JSON)
    cratory_base_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)
    rules_json: Mapped[dict] = mapped_column(JSON)

    ops: Mapped[list["PlanOp"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanOp(Base):
    __tablename__ = "plan_op"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    before_json: Mapped[dict] = mapped_column(JSON)
    after_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="pending")

    plan: Mapped["Plan"] = relationship(back_populates="ops")


class UndoJournal(Base):
    __tablename__ = "undo_journal"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), index=True)
    op_seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    from_path: Mapped[str | None] = mapped_column(String)
    to_path: Mapped[str | None] = mapped_column(String)
    prior_tags_json: Mapped[dict | None] = mapped_column(JSON)
    quarantine_path: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)
