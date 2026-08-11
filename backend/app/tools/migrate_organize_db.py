"""Migrazione del DB Organize (djorganizer.db) dentro quello Cratory (djassistant.db).

Migra scan_root, audio_file, plan, plan_op, undo_journal rimappando gli id.
NON migra issue e dup_group: sono derivati e li rigenera il primo scan.
NON tocca track_id/location/primary_file_id: sono colonne di F3.

La verifica è su invarianti calcolati dalla sorgente, mai su costanti: i numeri
del DB reale cambiano a ogni uso dell'app.

Uso:
    python -m app.tools.migrate_organize_db --src ../DjOrganizer01/backend/data/djorganizer.db \\
        --dest data/djassistant.db            # dry-run: stampa il report, non scrive
    python -m app.tools.migrate_organize_db --src … --dest … --apply
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# Ordine di travaso: le tabelle che fanno da bersaglio alle FK vengono prima.
_TABELLE = ("scan_root", "audio_file", "plan", "plan_op", "undo_journal")


@dataclass
class Report:
    sorgente: dict[str, int] = field(default_factory=dict)
    scan_root: int = 0
    audio_file: int = 0
    plan: int = 0
    plan_op: int = 0
    undo_journal: int = 0
    fk_orfane: int = 0
    dry_run: bool = True

    def ok(self) -> bool:
        return (
            self.fk_orfane == 0
            and all(getattr(self, t) == self.sorgente.get(t, 0) for t in _TABELLE)
        )

    def render(self) -> str:
        righe = [f"{'DRY-RUN' if self.dry_run else 'MIGRAZIONE'} — righe travasate"]
        for t in _TABELLE:
            atteso = self.sorgente.get(t, 0)
            ottenuto = getattr(self, t)
            segno = "ok" if atteso == ottenuto else "MISMATCH"
            righe.append(f"  {t:<14} {ottenuto:>6} / {atteso:<6} {segno}")
        righe.append(f"  {'FK orfane':<14} {self.fk_orfane:>6}")
        righe.append(f"  esito: {'OK' if self.ok() else 'FALLITO'}")
        return "\n".join(righe)


def _colonne(conn: sqlite3.Connection, tabella: str, schema: str = "main") -> list[str]:
    cur = conn.execute(f"PRAGMA {schema}.table_info({tabella})")
    return [r[1] for r in cur.fetchall()]


def migra(src_organize: Path, dest: Path, *, dry_run: bool) -> Report:
    """Travasa src_organize dentro dest. Con dry_run=True non scrive nulla:
    esegue tutto dentro una transazione e fa ROLLBACK."""
    src_organize = Path(src_organize)
    dest = Path(dest)
    if not src_organize.exists():
        raise FileNotFoundError(f"DB Organize non trovato: {src_organize}")
    if not dest.exists():
        raise FileNotFoundError(f"DB di destinazione non trovato: {dest}")

    conn = sqlite3.connect(dest)
    # isolation_level=None → autocommit: BEGIN/COMMIT/ROLLBACK espliciti
    # funzionano. Col default, sqlite3 apre transazioni implicite sulle DML e il
    # nostro BEGIN esploderebbe con "cannot start a transaction within a
    # transaction". ATTACH, per lo stesso motivo, va fatto fuori transazione.
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")  # travasiamo in ordine, controlliamo dopo
    conn.execute("ATTACH DATABASE ? AS org", (str(src_organize),))
    report = Report(dry_run=dry_run)

    try:
        # Precondizione, PRIMA di aprire la transazione: la destinazione dev'essere
        # vergine. È ciò che permette di conservare gli id originali senza tabella
        # di corrispondenza — vedi la nota sulla rimappatura nel piano.
        for tabella in _TABELLE:
            report.sorgente[tabella] = conn.execute(
                f"select count(*) from org.{tabella}"
            ).fetchone()[0]
            gia_presenti = conn.execute(f"select count(*) from main.{tabella}").fetchone()[0]
            if gia_presenti:
                raise RuntimeError(
                    f"main.{tabella} è già popolata ({gia_presenti} righe): "
                    "la destinazione non è vergine, migrazione annullata."
                )

        conn.execute("BEGIN")
        # Le colonne comuni alle due copie della tabella (la destinazione può
        # averne di più: ensure_schema crea lo schema corrente).
        for tabella in _TABELLE:
            comuni = [c for c in _colonne(conn, tabella, "org") if c in _colonne(conn, tabella)]
            lista = ", ".join(comuni)
            conn.execute(
                f"INSERT INTO main.{tabella} ({lista}) SELECT {lista} FROM org.{tabella}"
            )
            setattr(report, tabella, conn.execute(
                f"select count(*) from main.{tabella}"
            ).fetchone()[0])

        report.fk_orfane = _conta_fk_orfane(conn)

        if dry_run or not report.ok():
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except Exception:
        # La precondizione "destinazione vergine" scatta PRIMA del BEGIN: lì non
        # c'è transazione da annullare e ROLLBACK solleverebbe a sua volta,
        # mascherando l'errore vero.
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise
    finally:
        conn.execute("DETACH DATABASE org")
        conn.close()

    return report


def _conta_fk_orfane(conn: sqlite3.Connection) -> int:
    """Righe figlie che puntano a un padre inesistente dopo il travaso."""
    controlli = (
        "select count(*) from audio_file f "
        "where not exists (select 1 from scan_root r where r.id = f.root_id)",
        "select count(*) from plan_op o "
        "where not exists (select 1 from plan p where p.id = o.plan_id)",
        "select count(*) from plan_op o "
        "where not exists (select 1 from audio_file f where f.id = o.file_id)",
        "select count(*) from undo_journal u "
        "where not exists (select 1 from audio_file f where f.id = u.file_id)",
        "select count(*) from undo_journal u "
        "where not exists (select 1 from plan p where p.id = u.run_id)",
    )
    return sum(conn.execute(q).fetchone()[0] for q in controlli)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="djorganizer.db sorgente")
    parser.add_argument("--dest", required=True, type=Path, help="djassistant.db di destinazione (una COPIA)")
    parser.add_argument("--apply", action="store_true", help="scrive davvero (default: dry-run)")
    args = parser.parse_args()

    report = migra(args.src, args.dest, dry_run=not args.apply)
    print(report.render())
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
