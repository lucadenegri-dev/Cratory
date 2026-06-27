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
