"""Schemi Pydantic I/O validato."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    type: str
    field: str | None
    severity: str
    detail: str
    suggested_fix_json: dict | None
    status: str
    file_path: str
    artist: str | None
    title: str | None


class IssueStatusBody(BaseModel):
    status: str


class IssueBulkBody(BaseModel):
    type: str | None = None
    severity: str | None = None
    status: str


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


class PlanOpRead(BaseModel):
    id: int
    seq: int
    kind: str
    file_id: int
    file_path: str
    before: dict
    after: dict
    status: str


class ConflictRead(BaseModel):
    kind: str
    file_id: int
    detail: str


class PlanStats(BaseModel):
    n_retag: int = 0
    n_rename: int = 0
    n_move: int = 0
    n_delete: int = 0
    space_freed_bytes: int = 0
    n_conflicts: int = 0
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
