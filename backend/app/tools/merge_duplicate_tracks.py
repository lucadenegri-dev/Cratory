"""Fusione di due Track che puntano allo stesso file su disco.

Serve perché `audio_file.track_id` è una FK singola: due tracce sullo stesso
file renderebbero l'aggancio ambiguo e romperebbero la simmetria
`primary_file_id ↔ track_id`. Vedi il piano F3a.

Uso:
    python -m app.tools.merge_duplicate_tracks --elenca
    python -m app.tools.merge_duplicate_tracks --tenere 150 --scartare 1157 --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import Track, playlist_tracks


def trova_duplicati_per_path(db: Session) -> list[tuple[str, list[int]]]:
    """Path posseduti da più di una Track, con gli id coinvolti."""
    doppi = db.scalars(
        select(Track.local_path)
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
        .group_by(Track.local_path)
        .having(func.count() > 1)
    ).all()
    esito = []
    for path in doppi:
        ids = list(db.scalars(select(Track.id).where(Track.local_path == path)))
        esito.append((path, ids))
    return esito


def fondi(db: Session, *, tenere_id: int, scartare_id: int) -> dict[str, int]:
    """Sposta le membership di `scartare_id` su `tenere_id`, poi lo cancella.

    Non fa commit: il chiamante decide la transazione.
    """
    if tenere_id == scartare_id:
        raise ValueError("non si fonde una traccia con se stessa")
    tenere, scartare = db.get(Track, tenere_id), db.get(Track, scartare_id)
    if tenere is None or scartare is None:
        raise ValueError(f"traccia inesistente: {tenere_id if tenere is None else scartare_id}")

    gia_presenti = set(db.scalars(
        select(playlist_tracks.c.playlist_id).where(playlist_tracks.c.track_id == tenere_id)
    ))
    spostate = 0
    righe = db.execute(
        select(playlist_tracks).where(playlist_tracks.c.track_id == scartare_id)
    ).mappings().all()
    for riga in righe:
        if riga["playlist_id"] in gia_presenti:
            continue  # la PK composta (playlist_id, track_id) è già occupata
        db.execute(insert(playlist_tracks).values(
            playlist_id=riga["playlist_id"], track_id=tenere_id,
            added_at=riga["added_at"], added_by=riga["added_by"], position=riga["position"],
        ))
        spostate += 1
    db.execute(delete(playlist_tracks).where(playlist_tracks.c.track_id == scartare_id))
    db.delete(scartare)
    db.flush()
    return {"playlist_spostate": spostate}


def _sessione(db_path: str | None):
    """Sessione sul DB indicato, o su quello configurato. Stampa SEMPRE quale.

    Lanciato da un worktree, il default è il DB del worktree — non quello del
    checkout principale: uno strumento che non dice su cosa sta lavorando
    risponde "nessun duplicato" su un database vuoto e sembra aver funzionato.
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="path del DB su cui agire (default: quello configurato)")
    parser.add_argument("--elenca", action="store_true", help="mostra i duplicati e esce")
    parser.add_argument("--tenere", type=int)
    parser.add_argument("--scartare", type=int)
    parser.add_argument("--apply", action="store_true", help="scrive davvero (default: dry-run)")
    args = parser.parse_args()

    with _sessione(args.db) as db:
        if args.elenca or not (args.tenere and args.scartare):
            for path, ids in trova_duplicati_per_path(db):
                print(f"{path}  →  tracce {ids}")
            return 0
        esito = fondi(db, tenere_id=args.tenere, scartare_id=args.scartare)
        print(f"membership spostate: {esito['playlist_spostate']}")
        if args.apply:
            db.commit()
            print("fusione applicata")
        else:
            db.rollback()
            print("dry-run: nulla scritto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
