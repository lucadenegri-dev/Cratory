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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Track, playlist_tracks
from app.repositories import merge_tracks


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
    """Sposta su `tenere_id` cio' che era attaccato a `scartare_id`, poi lo cancella.

    Delega a `repositories.merge_tracks`, che e' la fusione vera dell'app (la usa
    anche il runner della coda quando il file appena scaricato collide per hash
    con un'altra traccia). Farsi qui una seconda fusione ridotta significava
    dimenticarsene pezzi: spostava solo le membership playlist, quindi una
    traccia usata in un set salvato o con storico nella coda download non si
    poteva fondere affatto — la DELETE finiva in IntegrityError sulle FK
    `setlist_tracks.track_id` / `download_queue_items.track_id`.

    Non fa commit: il chiamante decide la transazione.
    """
    if tenere_id == scartare_id:
        raise ValueError("non si fonde una traccia con se stessa")
    tenere, scartare = db.get(Track, tenere_id), db.get(Track, scartare_id)
    if tenere is None or scartare is None:
        raise ValueError(f"traccia inesistente: {tenere_id if tenere is None else scartare_id}")

    # Contato PRIMA della fusione: dopo, le righe di `scartare` non esistono
    # piu' e non si distinguerebbero le spostate da quelle gia' di `tenere`.
    # Stessa regola di merge_tracks: si sposta solo cio' che non c'e' gia'.
    gia_presenti = set(db.scalars(
        select(playlist_tracks.c.playlist_id).where(playlist_tracks.c.track_id == tenere_id)
    ))
    da_spostare = set(db.scalars(
        select(playlist_tracks.c.playlist_id).where(playlist_tracks.c.track_id == scartare_id)
    ))
    spostate = len(da_spostare - gia_presenti)

    merge_tracks(db, tenere, scartare)
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
