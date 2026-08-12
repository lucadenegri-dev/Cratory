"""Backfill di AudioFile.location, AudioFile.track_id e Track.primary_file_id.

Assert su invarianti, non su costanti: i numeri del DB reale cambiano a ogni
uso dell'app (in F2 erano già cambiati fra due misure nella stessa giornata).

Uso:
    python -m app.tools.backfill_track_files --db /path/a/djassistant.db
    python -m app.tools.backfill_track_files --db /path/a/djassistant.db --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.file_link import deriva_location


@dataclass
class Report:
    location_library: int = 0
    location_inbox: int = 0
    location_fuori: int = 0
    agganciati: int = 0
    primary: int = 0
    coppie_attese: int = 0
    dry_run: bool = True

    def ok(self) -> bool:
        return (
            self.location_fuori == 0
            and self.agganciati == self.primary          # simmetria delle due facce
            and self.agganciati == self.coppie_attese    # nessuna coppia persa
        )

    def render(self) -> str:
        return "\n".join([
            f"{'DRY-RUN' if self.dry_run else 'BACKFILL'}",
            f"  location=library   {self.location_library:>6}",
            f"  location=inbox     {self.location_inbox:>6}",
            f"  fuori dalle radici {self.location_fuori:>6}   (deve essere 0)",
            f"  track_id assegnati {self.agganciati:>6} / {self.coppie_attese} attesi",
            f"  primary_file_id    {self.primary:>6}   (deve uguagliare i track_id)",
            f"  esito: {'OK' if self.ok() else 'FALLITO'}",
        ])


def backfill(db: Session, *, library_root: str, inbox_root: str, dry_run: bool) -> Report:
    report = Report(dry_run=dry_run)

    # Quante coppie ci aspettiamo: il join per path assoluto, calcolato PRIMA
    # di toccare qualsiasi cosa. È l'invariante contro cui si misura l'esito.
    report.coppie_attese = db.scalar(
        select(func.count())
        .select_from(Track)
        .join(AudioFile, AudioFile.path == Track.local_path)
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    ) or 0

    per_path: dict[str, AudioFile] = {}
    for file in db.scalars(select(AudioFile)):
        try:
            loc = deriva_location(file.path, library_root=library_root, inbox_root=inbox_root)
        except ValueError:
            report.location_fuori += 1
            continue
        file.location = loc
        if loc == "library":
            report.location_library += 1
        else:
            report.location_inbox += 1
        per_path[file.path] = file

    for track in db.scalars(
        select(Track).where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    ):
        file = per_path.get(track.local_path)
        if file is None:
            continue
        file.track_id = track.id
        track.primary_file_id = file.id
        report.agganciati += 1
        report.primary += 1

    if dry_run or not report.ok():
        db.rollback()
    else:
        db.flush()
    return report


def _sessione(db_path: str | None):
    """Sessione sul DB indicato, o su quello configurato. Stampa SEMPRE quale.

    Stessa ragione di merge_duplicate_tracks: lanciato da un worktree il default
    è il DB del worktree, non quello del checkout principale.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    if db_path:
        engine = create_engine(f"sqlite:///{Path(db_path).resolve().as_posix()}")
    else:
        from app.db import engine  # type: ignore[no-redef]
    print(f"database: {engine.url}")
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def main() -> int:
    from app.core.config import settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="path del DB su cui agire (default: quello configurato)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with _sessione(args.db) as db:
        print(f"library_root: {settings.library_root or '(vuoto)'}")
        print(f"inbox_root:   {settings.slskd_download_dir or '(vuoto)'}")
        report = backfill(db, library_root=settings.library_root,
                          inbox_root=settings.slskd_download_dir,
                          dry_run=not args.apply)
        print(report.render())
        if args.apply and report.ok():
            db.commit()
            print("backfill applicato")
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
