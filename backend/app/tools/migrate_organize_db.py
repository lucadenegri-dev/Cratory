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

Se la sorgente contiene righe con una FK che punta a un target inesistente
(nella sorgente: il vecchio Organize girava con le foreign key spente), il
comportamento di default è fallire e basta — nessuna riga viene scartata in
silenzio. Per scartarle esplicitamente:
    python -m app.tools.migrate_organize_db --src … --dest … --apply --scarta-orfani
Con quel flag le righe orfane vengono escluse dal travaso e scritte per
intero (tutte le colonne) in un file JSONL accanto a --dest, il cui path è
stampato nel report. Se quel file non può essere scritto, la migrazione non
procede.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings

# Ordine di travaso: le tabelle che fanno da bersaglio alle FK vengono prima.
_TABELLE = ("scan_root", "audio_file", "plan", "plan_op", "undo_journal")

# FK dichiarate in app/organize/models.py: tabella figlia -> [(colonna, tabella padre), ...].
# scan_root e plan non hanno colonne FK proprie (sono solo bersaglio di altre).
_FK: dict[str, list[tuple[str, str]]] = {
    "audio_file": [("root_id", "scan_root")],
    "plan_op": [("plan_id", "plan"), ("file_id", "audio_file")],
    "undo_journal": [("run_id", "plan"), ("file_id", "audio_file")],
}


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
    # Attivato da --scarta-orfani: righe con FK non risolvibile nella sorgente
    # escluse dal travaso, per tabella.
    scarta_orfani: bool = False
    scartati: dict[str, int] = field(default_factory=dict)
    dump_path: str | None = None
    # Diagnosi sempre calcolata (con o senza il flag): (tabella, colonna, tabella_padre, righe_orfane).
    dettaglio_orfani: list[tuple[str, str, str, int]] = field(default_factory=list)

    def ok(self) -> bool:
        return self.fk_orfane == 0 and all(
            getattr(self, t) + self.scartati.get(t, 0) == self.sorgente.get(t, 0)
            for t in _TABELLE
        )

    def render(self) -> str:
        righe = [f"{'DRY-RUN' if self.dry_run else 'MIGRAZIONE'} — righe travasate"]
        for t in _TABELLE:
            atteso = self.sorgente.get(t, 0)
            migrati = getattr(self, t)
            scartati = self.scartati.get(t, 0)
            segno = "ok" if migrati + scartati == atteso else "MISMATCH"
            extra = f" (+{scartati} scartate)" if scartati else ""
            righe.append(f"  {t:<14} {migrati:>6}{extra} / {atteso:<6} {segno}")
        righe.append(f"  {'FK orfane':<14} {self.fk_orfane:>6}")

        problematici = [d for d in self.dettaglio_orfani if d[3] > 0]
        if self.scarta_orfani:
            if self.dump_path:
                totale = sum(self.scartati.values())
                righe.append(f"  righe scartate: {totale} — dump completo in: {self.dump_path}")
        elif problematici:
            righe.append(
                "  FK orfane nella sorgente (nessuna riga esclusa: usare --scarta-orfani "
                "per escluderle e ottenere un dump di ciò che verrebbe scartato):"
            )
            for tabella, colonna, padre, n in problematici:
                righe.append(f"    {tabella}.{colonna} -> {padre}.id: {n} righe orfane")

        righe.append(f"  esito: {'OK' if self.ok() else 'FALLITO'}")
        return "\n".join(righe)


def _colonne(conn: sqlite3.Connection, tabella: str, schema: str = "main") -> list[str]:
    cur = conn.execute(f"PRAGMA {schema}.table_info({tabella})")
    return [r[1] for r in cur.fetchall()]


def _percorso_dump_default(dest: Path) -> Path:
    """Un file accanto a --dest, mai dentro --dest: il dump delle righe
    scartate deve sopravvivere anche se la migrazione stessa fallisce dopo."""
    return dest.with_name(dest.stem + ".scartati.jsonl")


def migra(
    src_organize: Path,
    dest: Path,
    *,
    dry_run: bool,
    scarta_orfani: bool = False,
    dump_path: Path | None = None,
) -> Report:
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
            # Condizione SQL "la riga ha tutte le FK risolvibili nella sorgente"
            # per le tabelle che hanno colonne FK proprie (scan_root e plan non
            # ce l'hanno: sono solo bersaglio). Serve sia per la diagnosi (con o
            # senza il flag) sia, con --scarta-orfani, per filtrare l'INSERT e
            # selezionare le righe da scartare.
            condizioni_fk_valide: dict[str, str] = {}
            righe_scartate: dict[str, list[dict]] = {}
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

                # Diagnosi FK sempre calcolata (anche senza --scarta-orfani: è
                # quello che rende il messaggio d'errore del caso "fallisce"
                # utile invece che un generico "FK orfane: N"). Per costruzione
                # dello schema (app/organize/models.py) queste colonne sono
                # NOT NULL; "is not null" resta comunque una guardia a costo
                # zero contro sorgenti più vecchie/lasche.
                fks = _FK.get(tabella, [])
                for colonna, padre in fks:
                    n_orfane = conn.execute(
                        f"select count(*) from org.{tabella} o "
                        f"where o.{colonna} is not null "
                        f"and not exists (select 1 from org.{padre} p where p.id = o.{colonna})"
                    ).fetchone()[0]
                    report.dettaglio_orfani.append((tabella, colonna, padre, n_orfane))
                if fks:
                    condizioni_fk_valide[tabella] = " and ".join(
                        f"(o.{colonna} is null or exists "
                        f"(select 1 from org.{padre} p where p.id = o.{colonna}))"
                        for colonna, padre in fks
                    )
                    if scarta_orfani:
                        cur = conn.execute(
                            f"select * from org.{tabella} o "
                            f"where not ({condizioni_fk_valide[tabella]})"
                        )
                        nomi_colonne = [d[0] for d in cur.description]
                        righe_scartate[tabella] = [
                            dict(zip(nomi_colonne, riga)) for riga in cur.fetchall()
                        ]

            if problemi:
                raise RuntimeError("migrazione annullata:\n- " + "\n- ".join(problemi))

            report.scarta_orfani = scarta_orfani
            if scarta_orfani:
                # Il dump va scritto PRIMA di qualunque INSERT: se non può
                # essere scritto la migrazione non deve procedere, altrimenti
                # uno scarto senza traccia è esattamente ciò che l'operatore
                # vuole evitare. Un dump vuoto (nessuna riga orfana in questa
                # run) viene scritto comunque, per coerenza: il report indica
                # sempre dove guardare.
                percorso_dump = Path(dump_path) if dump_path is not None else _percorso_dump_default(dest)
                try:
                    with open(percorso_dump, "w", encoding="utf-8") as fh:
                        for tabella in _TABELLE:
                            for riga in righe_scartate.get(tabella, []):
                                fh.write(json.dumps({"tabella": tabella, **riga}, ensure_ascii=False, default=str))
                                fh.write("\n")
                except OSError as exc:
                    raise RuntimeError(
                        f"impossibile scrivere il dump delle righe scartate in {percorso_dump}: {exc}. "
                        "La migrazione non procede: uno scarto senza traccia non è ammesso."
                    ) from exc
                report.dump_path = str(percorso_dump)

            # Passaggio 2: adesso che nessuna tabella ha problemi noti, scrivi.
            for tabella in _TABELLE:
                comuni = colonne_comuni[tabella]
                lista = ", ".join(comuni)
                if scarta_orfani and tabella in condizioni_fk_valide:
                    filtro = f" WHERE {condizioni_fk_valide[tabella]}"
                else:
                    filtro = ""
                conn.execute(
                    f"INSERT INTO main.{tabella} ({lista}) SELECT {lista} FROM org.{tabella} o{filtro}"
                )
                setattr(report, tabella, conn.execute(
                    f"select count(*) from main.{tabella}"
                ).fetchone()[0])
                if scarta_orfani and tabella in righe_scartate:
                    report.scartati[tabella] = len(righe_scartate[tabella])

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
    parser.add_argument(
        "--scarta-orfani",
        action="store_true",
        dest="scarta_orfani",
        help=(
            "esclude dal travaso le righe con una FK non risolvibile nella sorgente "
            "(default: fallisce in presenza di orfani, non ne esclude nessuna). "
            "Scrive un dump JSONL di tutte le righe scartate accanto a --dest."
        ),
    )
    args = parser.parse_args()

    report = migra(args.src, args.dest, dry_run=not args.apply, scarta_orfani=args.scarta_orfani)
    print(report.render())
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
