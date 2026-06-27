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
