"""Schemi Pydantic I/O validato."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ScanSummary(BaseModel):
    roots: list[int]
    found: int = 0
    inserted: int = 0
    # Righe ri-toccate (last_scanned_at aggiornato), NON righe con contenuto cambiato.
    # Una re-scansione su disco immutato produce updated == N (file già noti).
    updated: int = 0
    moved: int = 0
    missing: int = 0
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScanRootCreate(BaseModel):
    path: str
    label: str | None = None


class ScanRootRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    label: str | None
    last_scanned_at: datetime | None
    file_count: int
    missing_count: int = 0


class AnalyzeSummary(BaseModel):
    issues_total: int = 0
    issues_by_severity: dict[str, int] = {}
    dup_groups: int = 0
    dup_files: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class IssueRead(BaseModel):
    id: int
    file_id: int
    root_id: int
    type: str
    field: str | None
    severity: str
    detail: str
    suggested_fix_json: dict | None
    status: str
    file_path: str
    artist: str | None
    title: str | None
    current_value: str | None = None
    is_new: bool = False


class IssueStatusBody(BaseModel):
    status: str


class IssueBulkBody(BaseModel):
    type: str | None = None
    severity: str | None = None
    status: str


class IssueFixBody(BaseModel):
    value: str


class FileTagsUpdate(BaseModel):
    """Modifica manuale dei tag da FILES: solo i campi presenti vengono toccati
    (il router usa `exclude_unset`). Valori grezzi; year/track parsati dal service."""
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: str | None = None
    label: str | None = None
    track_no: str | None = None
    comment: str | None = None


class ProviderSuggestBody(BaseModel):
    covers: bool = True


class IntegrityCheckBody(BaseModel):
    force: bool = False


class ProviderRescanBody(BaseModel):
    folder: str | None = None
    genre: str | None = None
    fields: list[str] = ["genre"]
    include_accepted: bool = False
    include_dismissed: bool = False
    covers: bool = False
    only_new: bool = False

    @field_validator("fields")
    @classmethod
    def _only_allowed(cls, v: list[str]) -> list[str]:
        allowed = {"genre", "album", "label", "year", "artist", "title"}
        bad = [f for f in v if f not in allowed]
        if bad:
            raise ValueError(f"campi non ammessi: {bad}")
        # I campi possono essere vuoti (es. rescan solo-cover): il core ricade
        # su 'genre' solo se non si chiedono nemmeno le copertine.
        return v


class DupMemberRead(BaseModel):
    file_id: int
    action: str
    path: str
    ext: str
    bitrate: int | None
    duration_s: float | None
    content_hash: str | None


class DupGroupRead(BaseModel):
    id: int
    match_kind: str
    keeper_file_id: int
    keeper_overridden: bool
    dismissed: bool
    members: list[DupMemberRead]


class KeeperBody(BaseModel):
    file_id: int


class RootTargetRead(BaseModel):
    id: int
    path: str
    label: str | None
    target_root: str | None


class SettingsRead(BaseModel):
    naming_template: str
    folder_template: str
    roots: list[RootTargetRead]


class SettingsUpdate(BaseModel):
    naming_template: str | None = None
    folder_template: str | None = None


class RootTargetUpdate(BaseModel):
    target_root: str | None = None


class LanguageSetting(BaseModel):
    language: Literal["it", "en"]


class PlanOpRead(BaseModel):
    id: int
    seq: int
    kind: str
    file_id: int
    file_path: str
    before: dict
    after: dict
    status: str
    skipped: bool = False  # in conflitto: all'apply verrà saltato, non blocca il piano


class ConflictRead(BaseModel):
    kind: str
    file_id: int
    detail: str


class PlanStats(BaseModel):
    n_retag: int = 0
    n_cover: int = 0
    n_rename: int = 0
    n_move: int = 0
    n_delete: int = 0
    space_freed_bytes: int = 0
    n_conflicts: int = 0
    n_skipped: int = 0
    # blocking = niente da applicare (tutti gli op in conflitto), non "c'è un conflitto"
    blocking: bool = False


class PlanRead(BaseModel):
    id: int
    status: str
    created_at: datetime
    rules: dict
    ops: list[PlanOpRead]
    conflicts: list[ConflictRead]
    stats: PlanStats


class ApplyResult(BaseModel):
    run_id: int | None = None
    applied_ops: int = 0
    skipped_ops: int = 0
    refused: bool = False
    stale: bool = False
    partial: bool = False
    failed_op_seq: int | None = None
    error: str | None = None
    reason: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class UndoResult(BaseModel):
    run_id: int
    reversed_ops: int = 0
    error: str | None = None


class HistoryItem(BaseModel):
    id: int
    status: str
    created_at: datetime
    n_ops: int


class LibraryStatsRead(BaseModel):
    files_total: int
    by_ext: dict[str, int]
    issues_by_severity: dict[str, int]
    dup_groups: int
    sources: int


class FileRow(BaseModel):
    id: int
    root_id: int
    path: str
    ext: str
    artist: str | None
    title: str | None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: int | None = None
    label: str | None = None
    track_no: int | None = None
    comment: str | None = None
    bitrate: int | None
    duration_s: float | None
    status: str
    issue_count: int
    worst_severity: str | None
    in_dup_group: bool
    # "embedded" = artwork nei tag, "provider" = solo una proposta in cache,
    # None = niente da mostrare (il frontend salta del tutto la richiesta).
    cover_source: str | None = None


class LibraryFacets(BaseModel):
    """Valori distinti per popolare i filtri per-tag della pagina FILES."""
    genre: list[str] = []
    artist: list[str] = []
    album: list[str] = []
    label: list[str] = []
    ext: list[str] = []
    year: list[int] = []


class ProviderInfo(BaseModel):
    """Stato di un provider esterno per la pagina Settings.
    status: 'configured' (chiave presente) | 'connected' (attivo senza chiave) |
    'missing' (non configurato)."""
    key: str
    name: str
    category: str
    description: str
    env_vars: list[str]
    docs_url: str
    status: str
