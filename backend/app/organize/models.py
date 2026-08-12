"""Modelli SQLAlchemy del chunk 1: radici di scan e file audio."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.db import Base
from app.models import Track  # risolve l'annotazione della relationship AudioFile.track


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# SCHEMA MORTO — decisione chiusa in F6, non un rinvio.
#
# Le sorgenti non sono più un'entità di dominio (F3b): esistono due cartelle,
# LIBRARY_ROOT e SLSKD_DOWNLOAD_DIR, e queste righe le rispecchiano soltanto.
# Le scrive solo app/organize/services/roots.py.
#
# La tabella e la colonna audio_file.root_id restano perché SQLite non può
# droppare root_id: è dentro uq_audio_root_path (indice interno non droppabile)
# e in una FK. Servirebbe un rebuild di audio_file, che ha quattro tabelle
# figlie (issue, dup_member, plan_op, undo_journal) — lo stesso rebuild che il
# progetto evita per tracks, e da cui F2 ha appena ripulito 158 righe orfane.
# Stessa scelta, e stessa ragione, di Track.playlist_id.
#
# F3b aveva rimandato la decisione a "dopo F4, se lo scanner richiederà comunque
# quel rebuild". F4 è passata e NON l'ha richiesto: il vincolo è identico,
# quindi la conclusione è identica e la questione è chiusa.
# Si riapre a una sola condizione: una modifica futura che richieda COMUNQUE il
# rebuild di audio_file per altri motivi. In quel caso root_id e scan_root
# escono insieme, a costo marginale zero.
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
    # SCHEMA MORTO: vedi la decisione in testa a ScanRoot, sopra.
    root_id: Mapped[int] = mapped_column(ForeignKey("scan_root.id"), index=True)
    # Traccia di cui questo file è una copia. NULL = file non ancora
    # riconosciuto (tipicamente l'inbox, dove i file non sono ancora tracce).
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id"), index=True)
    # Collocazione, derivata dal prefisso del path contro le due cartelle di
    # Settings: "inbox" (SLSKD_DOWNLOAD_DIR) o "library" (LIBRARY_ROOT).
    # Non esiste un terzo caso: lo scan cammina solo quelle due radici.
    location: Mapped[str] = mapped_column(String, default="inbox",
                                          server_default="inbox", index=True)
    path: Mapped[str] = mapped_column(String, index=True)
    ext: Mapped[str] = mapped_column(String)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Tempo di modifica all'ultima lettura completa del file. Insieme a
    # `size_bytes` è il segnale incrementale della fase 1: se path, dimensione e
    # mtime coincidono, il contenuto non è cambiato e non serve rileggerlo.
    # NULL = mai letto con questo meccanismo (prima corsa dopo la migrazione).
    mtime: Mapped[float | None] = mapped_column(Float)
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
    isrc: Mapped[str | None] = mapped_column(String)
    mbid: Mapped[str | None] = mapped_column(String, index=True)
    has_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    has_rating: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="present", index=True)
    scan_error: Mapped[str | None] = mapped_column(Text)
    integrity_ok: Mapped[bool | None] = mapped_column(Boolean)
    integrity_checked_hash: Mapped[str | None] = mapped_column(String)
    integrity_detail: Mapped[str | None] = mapped_column(Text)
    genre_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    root: Mapped["ScanRoot"] = relationship(back_populates="files")
    # La relazione vive qui, non su Track: così app/models.py non deve importare
    # app.organize. Il backref popola Track.files a runtime.
    # foreign_keys esplicito: fra audio_file e tracks ci sono DUE percorsi FK
    # (track_id di qua, primary_file_id di là), e l'ORM da solo non sa quale
    # regge questa relazione.
    track: Mapped["Track | None"] = relationship(
        "Track", foreign_keys="AudioFile.track_id",
        backref=backref("files", passive_deletes=False),
    )


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
    language: Mapped[str] = mapped_column(String, default="en")
    dedup_keep_rules_json: Mapped[dict | None] = mapped_column(JSON)
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
