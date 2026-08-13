"""Modifica manuale dei metadati di un file dalla schermata FILES.

A differenza dei fix da issue (che aspettano l'Apply), scrive i tag SUBITO sul
disco ed è reversibile: crea un Plan sintetico + una voce UndoJournal RETAG, così
la modifica compare in History e si annulla come una run qualsiasi. Ricalca il
pattern RETAG di services/apply.py: journal-first, poi mutazione, poi DB."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Track
from app.organize.integrations import tagio
from app.organize.models import AudioFile, Issue, Plan, UndoJournal, utcnow
from app.organize.services.planner import EDITABLE_TAG_FIELDS
from app.services.genre_align import align_track_genre

# Gli unici campi correggibili a mano: fonte unica in planner.EDITABLE_TAG_FIELDS.
_EDITABLE = frozenset(EDITABLE_TAG_FIELDS)
_INT_FIELDS = {"year", "track_no"}


class ManualEditError(Exception):
    """Errore di modifica manuale con codice/stato HTTP e `params` opzionali per la
    traduzione nel frontend; il router lo converte in api_error."""

    def __init__(self, status: int, code: str, message: str, params: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.params = params or {}


def _coerce(field: str, raw):
    """Normalizza un valore: stringa vuota/None → None (pulisce il tag);
    year/track_no → intero non negativo. Solleva ManualEditError(400)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None
    if field in _INT_FIELDS:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise ManualEditError(400, "value_invalid", f"'{field}' must be a number",
                                  {"field": field, "reason": "number"})
        if n < 0:
            raise ManualEditError(400, "value_invalid", f"'{field}' must be positive",
                                  {"field": field, "reason": "positive"})
        return n
    return str(raw)


def _norm(v):
    return None if v is None else str(v)


def edit_tags(db: Session, file: AudioFile, changes: dict) -> None:
    """Applica le modifiche manuali (field→valore) a `file`.
    Idempotente: i campi già uguali al DB sono ignorati. Dopo la scrittura ri-legge
    il disco e allinea il DB a ciò che è ATTERRATO davvero (alcuni formati non
    scrivono certi campi, es. comment su mp3): così DB e disco non divergono mai e
    non resta una run fantasma se nulla è cambiato sul file."""
    unknown = set(changes) - _EDITABLE
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise ManualEditError(400, "field_not_editable",
                              f"Field not editable: {fields}", {"fields": fields})
    if file.status != "present" or file.scan_error or not os.path.exists(file.path):
        raise ManualEditError(409, "file_not_writable", "File is not writable")

    coerced = {f: _coerce(f, changes[f]) for f in changes}
    # solo i campi il cui valore normalizzato differisce da quello nel DB
    effective = {f: v for f, v in coerced.items() if _norm(getattr(file, f)) != _norm(v)}
    if not effective:
        return

    # prior letti dal DISCO (come apply.py): l'undo ripristina lo stato reale.
    try:
        disk = tagio.read_tags(file.path)
    except tagio.TagReadError as exc:
        raise ManualEditError(409, "file_not_writable", str(exc))
    prior = {f: getattr(disk, f) for f in effective}

    # journal-first: Plan sintetico + voce RETAG PRIMA di toccare il file.
    plan = Plan(status="applied",
                rules_json={"kind": "manual_edit", "file_id": file.id,
                            "fields": sorted(effective)})
    db.add(plan)
    db.flush()
    journal = UndoJournal(run_id=plan.id, op_seq=0, kind="RETAG", file_id=file.id,
                          from_path=file.path, prior_tags_json=prior)
    db.add(journal)
    db.commit()

    try:
        tagio.write_tags(file.path, effective)      # poi muta il disco
    except tagio.TagWriteError as exc:
        # La scrittura è fallita: nulla è atterrato in modo affidabile → rimuovi la
        # run appena creata (come il ramo "nulla è atterrato"), niente run "applied"
        # fantasma in History. Errore controllato, col codice tradotto dal frontend.
        db.delete(journal)
        # Plan/UndoJournal senza relationship() ORM: serve un flush per l'ordine
        # FK-safe dei DELETE (dettaglio nel ramo gemello più sotto).
        db.flush()
        db.delete(plan)
        db.commit()
        raise ManualEditError(500, "tag_write_failed", str(exc))

    # Ri-leggi il disco e allinea il DB a ciò che è ATTERRATO: write_tags salta in
    # silenzio i campi che un formato non sa scrivere (es. comment su mp3), quindi
    # il valore richiesto non è affidabile — quello sul disco sì.
    try:
        written = tagio.read_tags(file.path)
    except tagio.TagReadError as exc:
        # Il disco È già mutato ma non riusciamo a verificare cosa sia atterrato:
        # codice distinto dalla scrittura fallita (DB non allineato → ri-scan concilia).
        raise ManualEditError(500, "tag_verify_failed", str(exc))
    landed = {f: getattr(written, f) for f in effective}
    for f, v in landed.items():
        setattr(file, f, v)

    changed = {f: v for f, v in landed.items() if _norm(v) != _norm(prior[f])}
    if not changed:
        # Niente è atterrato sul disco (es. solo comment su mp3): la run sarebbe
        # ingannevole e l'undo un no-op → rimuovi journal e Plan.
        db.delete(journal)
        # Plan/UndoJournal non hanno una relationship() ORM tra loro: senza un
        # flush qui, l'unit-of-work non sa ordinare i DELETE (nessun grafo di
        # dipendenza da seguire) e può tentare quello su plan prima di quello
        # su undo_journal, violando la FK di UndoJournal.run_id
        # (foreign_keys=ON dall'engine unificato F2).
        db.flush()
        db.delete(plan)
        db.commit()
        return

    # Restringi journal e Plan ai soli campi realmente cambiati sul disco (l'undo
    # non deve "ripristinare" un campo mai toccato).
    journal.prior_tags_json = {f: prior[f] for f in changed}
    plan.rules_json = {**plan.rules_json, "fields": sorted(changed)}
    _reconcile_issues(db, file.id, changed)
    # Sincronizzazione Parte 2 (regola condivisa col backfill e con lo scan):
    # se questo file e' agganciato a una traccia e il genere e' fra i campi
    # DAVVERO atterrati sul disco, tiene Track.genre allineato. Un tag genere
    # svuotato (None fra `changed`) non tocca nulla: la regola non sovrascrive
    # mai con un vuoto (il COALESCE di lettura ricadrebbe comunque sul valore
    # streaming, ma lo specchio in tabella non deve perdere l'ultimo noto).
    if "genre" in changed and file.track_id is not None:
        linked = db.get(Track, file.track_id)
        if linked is not None:
            align_track_genre(linked, changed["genre"], apply=True)
    db.commit()


def _reconcile_issues(db: Session, file_id: int, effective: dict) -> None:
    """Chiude le issue aperte sui campi appena modificati: manual vince su tutto
    (precedenza). Specchio di routers.issues.fix_issue."""
    issues = db.scalars(select(Issue).where(
        Issue.file_id == file_id, Issue.status == "open",
        Issue.field.in_(list(effective)))).all()
    for iss in issues:
        v = effective[iss.field]
        if v is None:
            iss.suggested_fix_json = {"field": iss.field, "action": "clear",
                                      "source": "manual"}
        else:
            iss.suggested_fix_json = {"field": iss.field, "action": "retag",
                                      "to": str(v), "source": "manual"}
        iss.status = "accepted"
        iss.updated_at = utcnow()
