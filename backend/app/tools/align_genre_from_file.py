"""Allineamento retroattivo una-tantum: `Track.genre` <- tag genere del primary file.

Il `COALESCE` di lettura (`app.repositories._EFFECTIVE_TAGS`) gia' mostra sempre
il genere corretto: questo tool sistema il DATO IN TABELLA, che resta uno
specchio di comodo (non la fonte di verita'). Perimetro: solo `genre`, mai
`title`/`artist`/`album`/`label`/`year` — vedi `app.services.genre_align` per
la regola condivisa anche dalla sincronizzazione di Organize (modifica manuale
dei tag + scansione), che tiene il dato allineato dopo questo backfill.

Uso:
  python -m app.tools.align_genre_from_file            # DRY-RUN: mostra cosa cambierebbe
  python -m app.tools.align_genre_from_file --apply    # applica le modifiche

Non modifica mai i file su disco: solo lettura del tag gia' indicizzato da
Organize (`AudioFile.genre`), nessun I/O aggiuntivo sul filesystem.
"""

from __future__ import annotations

import argparse

from app.db import SessionLocal, ensure_schema
from app.services.db_hygiene import align_owned_genre_from_file


def run(*, apply: bool, sample_limit: int = 20) -> dict:
    ensure_schema()
    db = SessionLocal()
    try:
        return align_owned_genre_from_file(db, apply=apply, sample_limit=sample_limit)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Allinea Track.genre al tag genere del primary file (retroattivo)."
    )
    parser.add_argument("--apply", action="store_true", help="Applica le modifiche (default: dry-run).")
    parser.add_argument("--sample", type=int, default=20,
                        help="Quante modifiche mostrare nel campione (default 20).")
    args = parser.parse_args()
    report = run(apply=args.apply, sample_limit=args.sample)

    mode = "APPLICATO" if args.apply else "DRY-RUN (nessuna scrittura)"
    print(f"== Allineamento genere possedute — {mode} ==")
    print(f"Tracce {'allineate' if args.apply else 'da allineare'}: {report['changed_tracks']}")
    if report["sample"]:
        print(f"Campione (prime {len(report['sample'])}):")
        for s in report["sample"]:
            print(f"  - #{s['id']}: {s['genre_before']!r} -> {s['genre_after']!r}")
    if not args.apply and report["changed_tracks"]:
        print("\nRilancia con --apply per scrivere.")


if __name__ == "__main__":
    main()
