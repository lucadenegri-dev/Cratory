"""Pulisce dati utente dal database locale.

Uso:
  python -m app.tools.clean_user_data library
  python -m app.tools.clean_user_data all --preserve-tokens --include-backups
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import text

from app.core.config import BACKEND_DIR, settings
from app.db import engine, ensure_schema

DATA_TABLES = ("setlist_tracks", "setlists", "tracks", "playlists", "enrichment_cache")
TOKEN_TABLES = ("spotify_tokens",)


def _sqlite_path() -> Path:
    if not settings.database_url.startswith("sqlite:///"):
        raise SystemExit("clean_user_data supporta solo il database SQLite locale.")
    return Path(settings.database_url.removeprefix("sqlite:///")).resolve()


def _counts(conn, tables: tuple[str, ...]) -> dict[str, int]:
    return {table: conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() for table in tables}


def _backup_files(db_path: Path) -> list[Path]:
    roots = {db_path.parent, BACKEND_DIR.parent / "data"}
    out: list[Path] = []
    for root in roots:
        if root.exists():
            out.extend(sorted(root.glob("*.bak")))
    return sorted({p.resolve() for p in out})


def _delete_backups(db_path: Path, *, dry_run: bool) -> list[str]:
    deleted: list[str] = []
    for path in _backup_files(db_path):
        deleted.append(str(path))
        if not dry_run:
            path.unlink(missing_ok=True)
    return deleted


def clean(mode: str, *, preserve_tokens: bool, include_backups: bool, dry_run: bool) -> dict:
    ensure_schema()
    effective_preserve_tokens = preserve_tokens or mode == "library"
    tables = DATA_TABLES + (() if effective_preserve_tokens else TOKEN_TABLES)
    db_path = _sqlite_path()
    with engine.begin() as conn:
        before = _counts(conn, DATA_TABLES + TOKEN_TABLES)
        if not dry_run:
            for table in tables:
                conn.execute(text(f"DELETE FROM {table}"))
    if not dry_run:
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM"))
    with engine.begin() as conn:
        after = _counts(conn, DATA_TABLES + TOKEN_TABLES)
    backups = _delete_backups(db_path, dry_run=dry_run) if include_backups else []
    return {
        "database": str(db_path),
        "mode": mode,
        "preserve_tokens": effective_preserve_tokens,
        "dry_run": dry_run,
        "before": before,
        "after": after,
        "deleted_backups": backups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulisce dati utente dal DB locale Cratory.")
    parser.add_argument("mode", choices=("library", "all"), nargs="?", default="library")
    parser.add_argument(
        "--preserve-tokens",
        action="store_true",
        help="In modalita' all mantiene i token OAuth Spotify.",
    )
    parser.add_argument("--include-backups", action="store_true", help="Elimina anche i file .bak nelle cartelle data note.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra cosa verrebbe cancellato senza modificare nulla.")
    args = parser.parse_args()
    report = clean(
        args.mode,
        preserve_tokens=args.preserve_tokens,
        include_backups=args.include_backups,
        dry_run=args.dry_run,
    )
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
