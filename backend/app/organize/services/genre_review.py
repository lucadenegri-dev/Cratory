"""Revisione generi su tutta la libreria: candidati dai provider come evidenza,
AI (con web search) per decidere, proposte come issue 'genre_review' oppure
riempimento delle issue genre già aperte. Sincrono e testabile: mb/discogs/ai_fn
sono iniettati (il job li costruisce). Mai due proposte aperte sullo stesso
campo di uno stesso file; i fix di origine provider e le decisioni utente
(accepted/dismissed) non si toccano."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.organize.models import AudioFile, Issue, utcnow
from app.organize.services.genre_norm import normalize_genre

GENRE_REVIEW_TYPE = "genre_review"
# Issue "da inspector" che il job può riempire invece di crearne una nuova.
_FILLABLE_TYPES = ("missing_metadata", "dirty_genre")
_BATCH = 10
# Dimensione della finestra di lavoro (lookup provider + commit), in multipli
# di batch_size: abbastanza grande da accumulare, ad ogni finestra, un
# ventaglio di tracce bisognose/coperte sufficiente a non sprecare budget di
# ricerca in sotto-batch minuscoli, abbastanza piccola da mantenere una
# resumabilità incrementale ragionevole (un crash a metà perde al più una
# finestra di lookup, non l'intera libreria). Con batch_size=10 di default
# la finestra è 50 file.
_WINDOW_MULTIPLIER = 5
# Tetto di ricerche per un sotto-batch "coperto" (tutte le tracce hanno già
# candidati dai provider): basso perché qui la ricerca è solo un ripiego per
# candidati implausibili, non un'esigenza sistematica. Fisso, non
# proporzionale alla dimensione del sotto-batch: un batch coperto da 10
# tracce non ha bisogno di più budget di uno da 3, l'evidenza c'è già per
# entrambi.
_COVERED_BUDGET = 2


def _candidates_stmt(folder: str | None, genre: str | None, redo: bool):
    stmt = select(AudioFile).where(AudioFile.status == "present")
    if folder:
        stmt = stmt.where(AudioFile.path.ilike(f"%{folder}%"))
    if genre:
        stmt = stmt.where(AudioFile.genre == genre)
    if not redo:
        stmt = stmt.where(AudioFile.genre_reviewed_at.is_(None))
    return stmt


def count_candidates(db: Session, *, folder: str | None = None,
                     genre: str | None = None, redo: bool = False) -> int:
    stmt = _candidates_stmt(folder, genre, redo)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _provider_candidates(f: AudioFile, *, mb, discogs) -> list[str]:
    """Candidati genere dai provider, normalizzati e deduplicati (ordine: MB
    per popolarità, poi Discogs). Discogs si interroga SOLO come gap-fill,
    quando MusicBrainz non ha prodotto candidati (stesso pattern di
    text_providers.resolve): senza token il suo limite è ~25 richieste/minuto,
    interrogarlo sempre su migliaia di file sprecherebbe un'ora di HTTP in 429
    sopra al già lento MusicBrainz (1 req/s). Gli errori/None dei provider
    sono tollerati."""
    raw: list[str] = []
    mb_res = mb.lookup(title=f.title, artist=f.artist,
                       isrc=(f.isrc.strip() or None) if f.isrc else None,
                       mbid=f.mbid) if mb is not None else None
    if mb_res:
        raw += mb_res.get("genre_candidates") or []
        if mb_res.get("genre_primary"):
            raw.append(mb_res["genre_primary"])
    if not raw and discogs is not None:
        dg_res = discogs.lookup(artist=f.artist, title=f.title)
        if dg_res:
            raw += dg_res.get("genre_candidates") or []
    out: list[str] = []
    for g in raw:
        n = normalize_genre(g)
        if n and n not in out:
            out.append(n)
    return out


def _apply_proposal(db: Session, f: AudioFile, proposal: dict) -> str:
    """Applica l'esito AI a un file. Ritorna la categoria per i contatori:
    'proposed' | 'confirmed' | 'unresolved' | 'skipped'."""
    value = normalize_genre(proposal.get("genre"))
    review_row = db.scalar(select(Issue).where(
        Issue.file_id == f.id, Issue.type == GENRE_REVIEW_TYPE,
        Issue.field == "genre"))

    def _drop_stale_review_row() -> None:
        """Una genre_review aperta è superata quando un'altra issue gestisce
        (o blocca) la proposta sullo stesso campo. Le decisioni utente
        (accepted/dismissed) non si toccano mai."""
        if review_row is not None and review_row.status == "open":
            db.delete(review_row)

    if value is None:
        return "unresolved"
    current = normalize_genre(f.genre)
    if current is not None and value.lower() == current.lower():
        _drop_stale_review_row()  # genere confermato: la proposta non serve più
        return "confirmed"

    level = proposal.get("level")
    fix = {"field": "genre", "action": "retag", "to": value,
           "source": "ai", "confidence": proposal.get("confidence", "low"),
           "level": level}
    # Il livello (track/release/artist) arriva anche nel detail mostrato in
    # ISSUES, così l'utente vede a colpo d'occhio se la proposta nasce da un
    # tag di traccia o solo dalla fama dell'artista. Stringa tecnica non
    # localizzata (stesso stile di "provider: {field} → {value}" in
    # provider_rescan.py), non va tradotta.
    detail = f"AI ({level}): genre → {value}" if level else f"AI: genre → {value}"
    open_rows = db.scalars(select(Issue).where(
        Issue.file_id == f.id, Issue.field == "genre",
        Issue.status == "open")).all()
    by_type = {r.type: r for r in open_rows}

    fillable = next((by_type[t] for t in _FILLABLE_TYPES if t in by_type), None)
    if fillable is not None:
        # La proposta è gestita da un'altra issue (inspector): la genre_review
        # eventualmente aperta sullo stesso campo è superata, sia che si
        # riesca a riempire fillable sia che si salti per priorità provider.
        _drop_stale_review_row()
        if (fillable.suggested_fix_json or {}).get("source") == "provider":
            return "skipped"  # provider > AI, mai sovrascrivere
        fillable.suggested_fix_json = fix
        fillable.updated_at = utcnow()
        return "proposed"
    if any(r.type != GENRE_REVIEW_TYPE for r in open_rows):
        _drop_stale_review_row()  # es. provider_override aperto: idem sopra
        return "skipped"  # niente doppioni
    if review_row is None:
        db.add(Issue(file_id=f.id, type=GENRE_REVIEW_TYPE, field="genre",
                     severity="info", detail=detail, suggested_fix_json=fix,
                     status="open"))
        return "proposed"
    if review_row.status == "open":
        review_row.suggested_fix_json = fix
        review_row.detail = detail
        review_row.updated_at = utcnow()
        return "proposed"
    return "skipped"  # accepted/dismissed: decisione utente


def _process_partition(db: Session, ai_fn, partition: list[tuple], *,
                       batch_size: int, always_search: bool, res: dict,
                       done: int, total: int, on_progress) -> int:
    """Spezza `partition` (coppie file/item già arricchite dei candidati
    provider, tutte bisognose o tutte coperte) in sotto-batch da al più
    batch_size elementi, chiama ai_fn una volta per sotto-batch col budget e
    la modalità appropriati, applica gli esiti e marca genre_reviewed_at.
    Un sotto-batch la cui chiamata AI solleva conta come unresolved e NON
    marca i suoi file (restano candidati per la passata successiva); non
    ferma gli altri sotto-batch né l'altra partizione. Committa dopo OGNI
    sotto-batch (Fix 3: granularità di resumabilità pari al sotto-batch, non
    alla finestra — un crash a metà finestra perde al più un sotto-batch,
    non le 5-6 chiamate AI già pagate della finestra intera). Ritorna il
    nuovo valore di `done`. Partizione vuota → nessuna chiamata (range(0,0,n)
    non itera, nessun commit)."""
    for start in range(0, len(partition), batch_size):
        sub = partition[start:start + batch_size]
        sub_files = [f for f, _ in sub]
        sub_items = [it for _, it in sub]
        budget = len(sub) if always_search else _COVERED_BUDGET
        try:
            results = ai_fn(sub_items, max_web_searches=budget,
                            always_search=always_search)
            ai_failed = False
        except Exception as exc:  # noqa: BLE001 — un sotto-batch fallito non ferma il job
            results = [None] * len(sub)
            ai_failed = True
            # Fix 4: anche un batch fallito può aver consumato ricerche web
            # (prima di arrendersi) — se l'eccezione le riporta (vedi
            # AiReviewError.web_searches) le contiamo comunque, invece di
            # perdere il costo di un tentativo che non ha prodotto un esito
            # utilizzabile. Un'eccezione qualunque che non ha l'attributo
            # (es. i RuntimeError dei test più vecchi) conta 0.
            res["web_searches"] += getattr(exc, "web_searches", 0) or 0
        else:
            # Stesso principio per il caso di successo: ai_fn può riportare
            # il conteggio come attributo sul valore di ritorno (vedi
            # ai_tags._ReviewResults); un ai_fn iniettato che ritorna una
            # list semplice non ha l'attributo -> 0, nessun errore.
            res["web_searches"] += getattr(results, "web_searches", 0) or 0
        for f, proposal in zip(sub_files, results):
            res[_apply_proposal(db, f, proposal or {})] += 1
            if not ai_failed:
                # Un sotto-batch fallito lascia i suoi file non marcati: la
                # passata successiva li riprende invece di darli per
                # "revisionati".
                f.genre_reviewed_at = utcnow()
        db.commit()
        done += len(sub)
        if on_progress is not None:
            on_progress(done, total, "reviewing")
    return done


def review(db: Session, *, mb, discogs, ai_fn, folder: str | None = None,
           genre: str | None = None, redo: bool = False,
           batch_size: int = _BATCH, on_progress=None) -> dict:
    """Loop principale, a finestre: per ogni finestra di file (multiplo di
    batch_size) fa le lookup provider, PARTIZIONA la finestra in bisognose
    (nessun candidato provider: _provider_candidates ha dato lista vuota) e
    coperte, forma sotto-batch da al più batch_size da ciascuna partizione,
    chiama l'AI una volta per sotto-batch col budget di ricerca appropriato
    (alto e imposto per le bisognose, basso e libero per le coperte). Il
    commit avviene per sotto-batch, dentro _process_partition (Fix 3), non
    più per finestra. La partizione esiste (non è una passata provider
    globale seguita da un partizionamento) così l'incrementalità resta: un
    crash a metà perde al più un sotto-batch, non l'intera finestra.

    `on_progress(processed, total, phase)`: `processed` è SEMPRE il numero
    di file effettivamente completati (mai una proiezione in avanti di
    lavoro non ancora finito) ed è monotono non decrescente — Fix 2. Durante
    la fase 'looking_up' resta fermo al valore dell'ultimo sotto-batch
    completato: la fase stessa comunica all'utente cosa sta succedendo, non
    serve (ed è disonesto) far avanzare il contatore per lookup ancora in
    corso, salvo poi farlo tornare indietro quando si passa a 'reviewing'."""
    files = db.scalars(_candidates_stmt(folder, genre, redo)).all()
    total = len(files)
    res = {"configured": True, "files": total, "proposed": 0, "confirmed": 0,
           "unresolved": 0, "skipped": 0, "web_searches": 0}
    done = 0
    window_size = batch_size * _WINDOW_MULTIPLIER
    for wstart in range(0, total, window_size):
        window = files[wstart:wstart + window_size]
        entries: list[tuple] = []
        for f in window:
            if on_progress is not None:
                # `done`, non `done + len(entries)`: le lookup in corso non
                # sono ancora tracce completate, quindi il contatore non
                # deve muoversi finché il sotto-batch che le comprende non è
                # stato effettivamente processato (vedi _process_partition).
                on_progress(done, total, "looking_up")
            entries.append((f, {
                "artist": f.artist, "title": f.title, "album": f.album,
                "label": f.label, "current_genre": f.genre,
                "candidates": _provider_candidates(f, mb=mb, discogs=discogs),
            }))
        if on_progress is not None:
            on_progress(done, total, "reviewing")
        needy = [e for e in entries if not e[1]["candidates"]]
        covered = [e for e in entries if e[1]["candidates"]]
        done = _process_partition(
            db, ai_fn, needy, batch_size=batch_size, always_search=True,
            res=res, done=done, total=total, on_progress=on_progress)
        done = _process_partition(
            db, ai_fn, covered, batch_size=batch_size, always_search=False,
            res=res, done=done, total=total, on_progress=on_progress)
    return res
