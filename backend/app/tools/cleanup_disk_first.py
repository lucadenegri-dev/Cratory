"""Pulizia una-tantum disk-first: allinea il DB alle regole attuali di Cratory.

Tre operazioni:
  1. Elimina i lead orfani (senza file, non in playlist né in un set salvato).
  2. Azzera sui lead i campi residui legacy (genre/bpm/camelot_key/energy).
  3. Riallinea le possedute al disco (rilegge i tag; disco autorevole).

Uso:
  python -m app.tools.cleanup_disk_first            # DRY-RUN: mostra cosa cambierebbe
  python -m app.tools.cleanup_disk_first --apply    # applica le modifiche

Non modifica mai i file su disco: solo lettura dei tag.
"""

from __future__ import annotations

import argparse

from app.db import SessionLocal, ensure_schema
from app.repositories import delete_orphan_leads, orphan_lead_ids
from app.services.db_hygiene import purge_lead_residue, realign_owned_from_disk


def run(*, apply: bool) -> dict:
    ensure_schema()
    db = SessionLocal()
    try:
        # 1) Lead orfani (eliminati prima, così non li si conta anche come residui).
        orphan_ids = orphan_lead_ids(db)
        orphans = len(orphan_ids)
        if apply and orphan_ids:
            delete_orphan_leads(db)
            db.commit()

        # 2) Residui legacy sui lead rimasti.
        residue = purge_lead_residue(db, apply=apply)

        # 3) Possedute allineate al disco.
        owned = realign_owned_from_disk(db, apply=apply)
    finally:
        db.close()
    return {"dry_run": not apply, "orphan_leads_deleted": orphans, "lead_residue": residue, "owned_realign": owned}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulizia disk-first del DB Cratory.")
    parser.add_argument("--apply", action="store_true", help="Applica le modifiche (default: dry-run).")
    args = parser.parse_args()
    report = run(apply=args.apply)

    mode = "APPLICATO" if args.apply else "DRY-RUN (nessuna scrittura)"
    print(f"== Pulizia disk-first — {mode} ==")
    print(f"Lead orfani {'eliminati' if args.apply else 'da eliminare'}: {report['orphan_leads_deleted']}")
    print("Residui legacy sui lead (azzerati per campo):")
    for field, n in report["lead_residue"].items():
        print(f"  - {field}: {n}")
    o = report["owned_realign"]
    print("Possedute allineate al disco:")
    print(f"  - tracce cambiate: {o['changed_tracks']}")
    print(f"  - campi cambiati:  {o['changed_fields']}")
    print(f"  - file mancanti (saltate): {o['missing_file']}")
    if not args.apply:
        print("\nNota: in dry-run i residui sui lead includono anche i lead che verranno")
        print("eliminati come orfani; dopo --apply quei conteggi possono risultare minori.")


if __name__ == "__main__":
    main()
