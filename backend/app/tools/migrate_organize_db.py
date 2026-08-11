"""Migrazione del DB Organize (djorganizer.db) dentro quello Cratory (djassistant.db).

Migra scan_root, audio_file, plan, plan_op, undo_journal preservando gli id.
NON migra issue e dup_group: sono derivati e li rigenera il primo scan.
NON tocca track_id/location/primary_file_id: sono colonne di F3.

La verifica è su invarianti calcolati dalla sorgente, mai su costanti: i numeri
del DB reale cambiano a ogni uso dell'app.

Uso (--dest è sempre una COPIA del DB Cratory, mai il file vero: anche il
dry-run apre --dest in scrittura e prende un write lock su di esso):
    python -m app.tools.migrate_organize_db --src ../DjOrganizer01/backend/data/djorganizer.db \\
        --dest /tmp/djassistant-copia.db      # dry-run: stampa il report, non scrive
    python -m app.tools.migrate_organize_db --src … --dest /tmp/djassistant-copia.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings

# Ordine di travaso: le tabelle che fanno da bersaglio alle FK vengono prima.
_TABELLE = ("scan_root", "audio_file", "plan", "plan_op", "undo_journal")


def _path_db_produzione() -> Path | None:
    """Il path del DB configurato in produzione (app.core.config.settings),
    solo se è uno sqlite su file reale. None per ':memory:' o URL non-sqlite
    (nessun altro backend è usato oggi, ma non è questa la funzione che deve
    deciderlo)."""
    url = settings.database_url
    if not url.startswith("sqlite:///") or url == "sqlite:///:memory:":
        return None
    return Path(url.removeprefix("sqlite:///"))


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

    # Ultima rete prima di lanciare lo script sui dati veri: --dest deve
    # sempre essere una copia. Confrontiamo path risolti (non stringhe grezze)
    # perché --dest può arrivare relativo o con '..'/symlink.
    prod = _path_db_produzione()
    if prod is not None and dest.resolve() == prod.resolve():
        raise RuntimeError(
            f"--dest ({dest}) risolve al DB di produzione configurato "
            f"({prod}): --dest deve essere sempre una COPIA, mai il file vero."
        )

    # uri=True abilita il riconoscimento degli URI anche per l'ATTACH successivo
    # (il flag SQLITE_OPEN_URI si applica alla connessione, non al singolo open):
    # è quello che ci permette di attaccare la sorgente in sola lettura sotto.
    conn = sqlite3.connect(str(dest), uri=True)
    report = Report(dry_run=dry_run)
    try:
        # isolation_level=None → autocommit: BEGIN/COMMIT/ROLLBACK espliciti
        # funzionano. Col default, sqlite3 apre transazioni implicite sulle DML
        # e il nostro BEGIN esploderebbe con "cannot start a transaction within
        # a transaction". ATTACH, per lo stesso motivo, va fatto fuori transazione.
        conn.isolation_level = None
        conn.execute("PRAGMA foreign_keys = OFF")  # travasiamo in ordine, controlliamo dopo
        # Sorgente attaccata in sola lettura: nessuna istruzione dello script ci
        # scrive (sono tutti SELECT), ma senza mode=ro SQLite può comunque
        # scrivere sul file attaccato per conto suo. Verificato empiricamente:
        # se la sorgente è in journal_mode=WAL con un -wal non ancora
        # checkpointato (il caso reale: app/db.py:24 forza WAL, e uno stop non
        # pulito di Organize lascia frame WAL pendenti), attaccarla in
        # scrittura e poi fare DETACH esegue un checkpoint completo — il .db
        # cresce (4096 -> 8192 byte) e il -wal si azzera — senza che lo
        # script esegua una sola scrittura logica. I conteggi restano
        # identici attraverso quel checkpoint, quindi non è un mismatch che
        # il Report intercetterebbe: mode=ro è l'unica cosa che lo rende
        # strutturalmente impossibile — un tentativo di scrittura diventa
        # "attempt to write a readonly database". Vedi
        # test_dry_run_non_scrive_non_altera_bytewise per la verifica a
        # livello di byte (non di conteggio) di questa proprietà.
        org_uri = src_organize.resolve().as_uri() + "?mode=ro"
        conn.execute("ATTACH DATABASE ? AS org", (org_uri,))

        conn.execute("BEGIN")
        try:
            # Passaggio 1: diagnosi completa su tutte le tabelle prima di
            # qualunque INSERT. Farlo dentro il ciclo che scrive fermerebbe
            # l'operatore alla prima tabella colpevole, con fino a quattro
            # tabelle già travasate (e da far rollback) prima di scoprire un
            # quinto problema al prossimo tentativo — su una run one-shot sui
            # dati veri, meglio vedere tutti i problemi in un colpo.
            problemi: list[str] = []
            colonne_comuni: dict[str, list[str]] = {}
            for tabella in _TABELLE:
                # Dentro la transazione: osservare "vuota" e poi scrivere
                # devono condividere lo snapshot, altrimenti un writer
                # concorrente fra i due passi vanificherebbe il controllo.
                report.sorgente[tabella] = conn.execute(
                    f"select count(*) from org.{tabella}"
                ).fetchone()[0]

                # Precondizione: la destinazione dev'essere vergine. È ciò che
                # permette di conservare gli id originali senza tabella di
                # corrispondenza — vedi la nota sulla preservazione nel piano.
                gia_presenti = conn.execute(f"select count(*) from main.{tabella}").fetchone()[0]
                if gia_presenti:
                    problemi.append(
                        f"main.{tabella} è già popolata ({gia_presenti} righe): "
                        "la destinazione non è vergine."
                    )

                # Le colonne comuni alle due copie della tabella (la destinazione
                # può averne di più: ensure_schema crea lo schema corrente). Una
                # colonna presente SOLO nella sorgente sparirebbe in silenzio —
                # inaccettabile per una migrazione one-shot di dati insostituibili
                # — quindi va rilevata e bloccata, non lasciata scomparire dietro
                # un "ok".
                colonne_org = _colonne(conn, tabella, "org")
                colonne_dest = _colonne(conn, tabella)
                mancanti = set(colonne_org) - set(colonne_dest)
                if mancanti:
                    problemi.append(
                        f"{tabella}: colonne presenti solo nella sorgente e che la "
                        f"migrazione perderebbe: {sorted(mancanti)}"
                    )
                colonne_comuni[tabella] = [c for c in colonne_org if c in colonne_dest]

            if problemi:
                raise RuntimeError("migrazione annullata:\n- " + "\n- ".join(problemi))

            # Passaggio 2: adesso che nessuna tabella ha problemi noti, scrivi.
            for tabella in _TABELLE:
                comuni = colonne_comuni[tabella]
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
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                # SQLite fa auto-rollback su SQLITE_FULL/IOERR/NOMEM o
                # interrupt: dopo un auto-rollback la transazione non è più
                # attiva, e un ROLLBACK esplicito solleva "cannot rollback -
                # no transaction is active", mascherando l'eccezione vera
                # (quella che l'operatore deve vedere). Nessun dato perso:
                # l'auto-rollback garantisce che nulla sia stato scritto.
                pass
            raise
        finally:
            conn.execute("DETACH DATABASE org")
    finally:
        conn.close()

    return report


def _conta_fk_orfane(conn: sqlite3.Connection) -> int:
    """Righe figlie che puntano a un padre inesistente dopo il travaso."""
    controlli = (
        "select count(*) from main.audio_file f "
        "where not exists (select 1 from main.scan_root r where r.id = f.root_id)",
        "select count(*) from main.plan_op o "
        "where not exists (select 1 from main.plan p where p.id = o.plan_id)",
        "select count(*) from main.plan_op o "
        "where not exists (select 1 from main.audio_file f where f.id = o.file_id)",
        "select count(*) from main.undo_journal u "
        "where not exists (select 1 from main.audio_file f where f.id = u.file_id)",
        "select count(*) from main.undo_journal u "
        "where not exists (select 1 from main.plan p where p.id = u.run_id)",
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
