"""Schemi Pydantic I/O validato."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LinkingReport(BaseModel):
    """Esito della fase 2 dello scan (aggancio tracce ai file indicizzati).

    Era un `dict` non tipizzato esposto tal quale in JSON, con tre forme
    possibili e nessun contratto: qui diventa verificabile da entrambe le
    sponde. `ScanSummary.linking = None` significa "fase non eseguita" — uno
    scan ristretto all'inbox si ferma alla fase 1.
    """

    scanned: int = 0
    matched: int = 0
    created: int = 0
    relinked: int = 0
    lost: int = 0
    orphans_removed: int = 0
    created_ids: list[int] = Field(default_factory=list)
    # Ricalcolo dell'energia: assente se la fase non è girata (radice smontata).
    energy_computed: int | None = None

    # Contatori della sola libreria. Il giro d'archivio ha i propri, tenuti
    # separati: `unchanged` di libreria (riga già agganciata e invariata) e
    # `unchanged` d'archivio (file scartato già visto) non sono la stessa cosa,
    # e sommarli sotto una chiave sola dava un numero che non significava nulla.
    unchanged: int = 0
    duplicates: int = 0
    failed: int = 0
    archive_unchanged: int = 0
    archive_duplicates: int = 0
    archive_failed: int = 0
    # Tracce marcate come scartate dal giro d'archivio: lo produce solo quello,
    # quindi non ha un gemello di libreria.
    archived: int = 0
    errors: list[dict] = Field(default_factory=list)


class ScanSummary(BaseModel):
    roots: list[int]
    found: int = 0
    inserted: int = 0
    # Righe ri-toccate perché rilette per intero (mtime/size cambiati, o riga
    # nuova/con scan_error). NON conta i file saltati dal fast-path incremental:
    # quelli sono in `unchanged`.
    updated: int = 0
    # File il cui (path, size_bytes, mtime) combacia con la riga esistente:
    # _scan_file_fields NON è stato richiamato, solo status/last_scanned_at
    # sono stati ritoccati. Una re-scansione su disco immutato produce
    # unchanged == N (file già noti) e updated == 0.
    unchanged: int = 0
    moved: int = 0
    missing: int = 0
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Report combinato delle quattro parti dell'aggancio (collega_tracce +
    # indicizza_archivio, se configurato + riconcilia_possessi +
    # recompute_energy). None finché la fase 2 non è ancora girata.
    linking: LinkingReport | None = None


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
    location: str
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


class GenreReviewBody(BaseModel):
    folder: str | None = None
    genre: str | None = None
    redo: bool = False


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


class SettingsRead(BaseModel):
    naming_template: str
    folder_template: str


class SettingsUpdate(BaseModel):
    naming_template: str | None = None
    folder_template: str | None = None


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
    kind: str | None = None


class LibraryStatsRead(BaseModel):
    files_total: int
    by_ext: dict[str, int]
    issues_by_severity: dict[str, int]
    dup_groups: int
    sources: int


class FileRow(BaseModel):
    id: int
    location: str
    path: str
    ext: str
    # Traccia agganciata (per il cross-link "apri traccia" dalla pagina FILES).
    track_id: int | None = None
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
