"""Schemi Pydantic I/O validato."""

from datetime import datetime

from pydantic import BaseModel


class ScanSummary(BaseModel):
    roots: list[int]
    found: int = 0
    inserted: int = 0
    updated: int = 0
    moved: int = 0
    missing: int = 0
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
