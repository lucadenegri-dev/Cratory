import csv
import io
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import SessionLocal, get_db
from app.integrations.llm import LLMError, LLMNotConfigured, get_llm_client, llm_configured
from app.repositories import (
    effective_genres_for_tracks,
    file_tags_for_tracks,
    get_playlist,
    get_setlist,
    list_setlists,
)
from app.schemas import (
    AddTrackRequest,
    AlternativesRequest,
    AlternativesResponse,
    GenerateAsyncStartOut,
    GenerateStatusOut,
    ManualSetCreate,
    ManualSetOut,
    MaterialItemOut,
    MaterialOut,
    MoveTrackRequest,
    ReplaceTrackRequest,
    RowMoveRequest,
    RowPatchRequest,
    RowsInsertRequest,
    SetGenerationRequest,
    SetlistOut,
    SetlistSummaryOut,
    SetRenameRequest,
)
from app.serializers import alternative_out, manual_set_out, setlist_out, setlist_summary_out, track_out
from app.services.ai_curation import run_curated_generation
from app.services.alternatives import AlternativesError, find_alternatives
from app.services.app_state import get_language
from app.services.manual_material import material_for
from app.services.manual_set import (
    ManualSetError,
    ManualSetNotFound,
    ManualSetNotManual,
    RevisionConflict,
    RowNotFound,
    create_manual_set,
    insert_rows,
    load_manual_set,
    move_row,
    remove_row,
    update_row_note,
)
from app.services.set_editor import (
    SetEditError,
    add_track,
    delete_set,
    move_track,
    move_track_to,
    remove_track,
    rename_set,
    replace_track,
)
from app.services.export_render import fmt_duration, render_m3u8
from app.services.scoring import classify_transition, mixing_tip, opening_track_label
from app.services.set_generator import SetGenerationError, generate_set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sets", tags=["sets"])


def _should_use_ai(req: SetGenerationRequest) -> bool:
    if req.use_ai is True:
        return True
    if req.use_ai is False:
        return False
    # auto: AI solo se configurata e c'e' un prompt libero da interpretare
    return llm_configured() and bool(req.prompt and req.prompt.strip())


# Fase mostrata durante la generazione deterministica (non-AI); le fasi del
# path AI sono già bilingui in ai_curation.py (_CURATION_PHASES).
_BUILDING_SET_PHASE = {"it": "Costruisco il set", "en": "Building the set"}

# --- Generazione asincrona (la generazione AI puo' richiedere ~1-3 min) -------
# App locale mono-utente: un job alla volta, stato in memoria con lock.
_gen_lock = threading.Lock()
_gen_state: dict = {
    "status": "idle",  # idle | running | done | error
    "phase": None,
    "using_ai": False,
    "setlist_id": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def _run_generation(req: SetGenerationRequest, use_ai: bool) -> None:
    db = SessionLocal()
    try:
        if use_ai:
            setlist = run_curated_generation(
                db, req, get_llm_client(),
                on_phase=lambda p: _gen_state.update(phase=p),
            )
        else:
            lang = get_language(db)
            _gen_state["phase"] = _BUILDING_SET_PHASE.get(lang, _BUILDING_SET_PHASE["it"])
            setlist = generate_set(db, req)
        _gen_state.update(status="done", setlist_id=setlist.id, phase=None)
        logger.info("Job generazione completato: set %s (%s)", setlist.id, setlist.generated_by)
    except (LLMError, LLMNotConfigured, SetGenerationError) as exc:
        _gen_state.update(status="error", error=str(exc))
        logger.error("Job generazione fallito: %s", exc)
    except Exception as exc:  # noqa: BLE001
        _gen_state.update(status="error", error=str(exc))
        logger.exception("Job generazione fallito (inatteso)")
    finally:
        _gen_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


@router.post("/generate-async", response_model=GenerateAsyncStartOut)
def generate_async(req: SetGenerationRequest):
    """Avvia la generazione in background e ritorna subito. Seguire /generate-status."""
    use_ai = _should_use_ai(req)
    if use_ai and not llm_configured():
        raise api_error(409, "ai_not_configured", "AI not configured: ANTHROPIC_API_KEY missing.",
                         reason="ANTHROPIC_API_KEY mancante")
    with _gen_lock:
        if _gen_state["status"] == "running":
            # Mai inghiottire una richiesta nuova nel job in corso: quel job puo' avere
            # un motore diverso (es. AI) da quello appena chiesto dall'utente.
            raise api_error(
                409, "set_generation_in_progress",
                "A generation is already running: wait for it to finish and try again.",
            )
        _gen_state.update(status="running", phase=None, using_ai=use_ai, setlist_id=None,
                          error=None, started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    threading.Thread(target=_run_generation, args=(req, use_ai), daemon=True).start()
    return {"status": "running", "phase": None, "using_ai": use_ai}


@router.get("/generate-status", response_model=GenerateStatusOut)
def generate_status():
    return dict(_gen_state)


def _require_generated(setlist) -> None:
    """Le rotte dell'editor classico assumono la forma di un set generato
    (righe sempre con `track`, indicizzabili per `position`): un set manuale
    puo' avere righe varco (`track` None) e blocchi (`block_id` fuori dalla
    numerazione lineare), quindi va rifiutato qui con lo stesso errore di
    dominio di `GET /{id}` invece di far arrivare un AttributeError o
    scombinare in silenzio il percorso costruito a mano."""
    if setlist.kind == "manual":
        raise api_error(409, "set_is_manual", "This set is manual: use /manual")


def _manual_error(exc: ManualSetError) -> HTTPException:
    if isinstance(exc, RevisionConflict):
        return api_error(409, "set_revision_conflict",
                         f"The set changed (revision {exc.current}): reload and retry.", current=exc.current)
    if isinstance(exc, ManualSetNotFound):
        return api_error(404, "set_not_found", "Set not found")
    if isinstance(exc, ManualSetNotManual):
        return api_error(409, "set_not_manual", "This set was generated: open it in the classic editor")
    if isinstance(exc, RowNotFound):
        return api_error(404, "set_row_not_found", "Row not found")
    if "Playlist not found" in str(exc):
        return api_error(404, "playlist_not_found", "Playlist not found")
    return api_error(422, "manual_set_error", f"Manual set error: {exc}", reason=str(exc))


@router.post("/manual", response_model=ManualSetOut, status_code=201)
def create_manual(req: ManualSetCreate, db: Session = Depends(get_db)):
    """Set preparato a mano, vuoto, con la playlist di origine letta aggiornata."""
    try:
        return manual_set_out(create_manual_set(db, name=req.name, playlist_id=req.playlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.get("", response_model=list[SetlistSummaryOut])
def get_all(db: Session = Depends(get_db)):
    return [setlist_summary_out(s) for s in list_setlists(db)]


@router.get("/{setlist_id}", response_model=SetlistOut)
def get_one(setlist_id: int, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    return setlist_out(setlist, get_language(db), db=db)


@router.get("/{setlist_id}/manual", response_model=ManualSetOut)
def get_manual(setlist_id: int, db: Session = Depends(get_db)):
    try:
        return manual_set_out(load_manual_set(db, setlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.get("/{setlist_id}/material", response_model=MaterialOut)
def get_material(setlist_id: int, q: str | None = Query(default=None, max_length=200),
                 owned: bool = False, unused: bool = False, db: Session = Depends(get_db)):
    """Playlist di origine aggiornata + tracce nel set + (con q) ricerca in libreria."""
    try:
        setlist = load_manual_set(db, setlist_id)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
    items = material_for(db, setlist, q=q, owned=owned, unused=unused)
    ft_map = file_tags_for_tracks(db, [t.id for t, _, _ in items])
    playlist = get_playlist(db, setlist.source_playlist_id) if setlist.source_playlist_id else None
    return MaterialOut(
        playlist_id=setlist.source_playlist_id,
        playlist_name=playlist.name if playlist is not None else None,
        items=[MaterialItemOut(track=track_out(t, ft_map.get(t.id)), in_set=in_set, from_playlist=fp)
               for t, in_set, fp in items],
    )


@router.post("/{setlist_id}/rows", response_model=ManualSetOut)
def rows_insert(setlist_id: int, req: RowsInsertRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(insert_rows(
            db, setlist_id, expected_revision=req.expected_revision,
            track_ids=req.track_ids, gap=req.gap, after_row_id=req.after_row_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/move", response_model=ManualSetOut)
def rows_move(setlist_id: int, row_id: int, req: RowMoveRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(move_row(
            db, setlist_id, row_id, expected_revision=req.expected_revision, position=req.position), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.patch("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_patch(setlist_id: int, row_id: int, req: RowPatchRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(update_row_note(
            db, setlist_id, row_id, expected_revision=req.expected_revision, note=req.note), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_delete(setlist_id: int, row_id: int, expected_revision: int = Query(ge=0),
                db: Session = Depends(get_db)):
    try:
        return manual_set_out(remove_row(db, setlist_id, row_id, expected_revision=expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/export", response_class=PlainTextResponse)
def export(
    setlist_id: int,
    format: str = Query(default="text", pattern="^(text|csv|markdown|m3u8)$"),
    db: Session = Depends(get_db),
):
    """Export del set: testo, CSV, Markdown o M3U8 (playlist Rekordbox). Export playlist Spotify: endpoint dedicato."""
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    lang = get_language(db)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["position", "role", "title", "artist", "bpm", "key", "duration_seconds",
                         "source", "spotify_id", "url", "transition_score", "risk_level",
                         "transition_class", "local_path"])
        # I4: stesso genere effettivo di setlist_out per la classificazione del reset.
        genre_map = effective_genres_for_tracks(db, [st.track_id for st in setlist.tracks])
        prev = None
        for st in setlist.tracks:
            t = st.track
            cls = (classify_transition(prev, t, lang, score=st.transition_score, genre_map=genre_map).label
                   if prev is not None else "")
            writer.writerow([st.position, st.role or "", t.title or "", t.artist or "", t.bpm or "",
                             t.camelot_key or "", t.duration_seconds or "", t.source_type,
                             t.spotify_id or "", t.url or "", st.transition_score or "", st.risk_level or "",
                             cls, t.local_path or ""])
            prev = t
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    if format == "markdown":
        md = [f"# {setlist.name}", ""]
        if setlist.global_explanation:
            md += [setlist.global_explanation, ""]
        md += ["| # | Ruolo | Traccia | BPM | Key | Durata | Transizione |",
               "|--:|---|---|--:|---|--:|---|"]
        prev = None
        for st in setlist.tracks:
            t = st.track
            label = f"{t.artist or '?'} — {t.title or t.spotify_id or '?'}"
            # Nota di mix deterministica e accurata (mai il log grezzo o claim AI non verificati).
            note = (mixing_tip(prev, t, lang) if prev is not None else opening_track_label(lang)).replace("|", "/").replace("\n", " ")
            prev = t
            md.append(
                f"| {st.position} | {st.role or ''} | {label} | "
                f"{t.bpm:.0f} | {t.camelot_key or '?'} | {fmt_duration(t.duration_seconds)} | {note} |"
                if t.bpm else
                f"| {st.position} | {st.role or ''} | {label} | — | "
                f"{t.camelot_key or '?'} | {fmt_duration(t.duration_seconds)} | {note} |"
            )
        return PlainTextResponse("\n".join(md), media_type="text/markdown")

    if format == "m3u8":
        # Playlist importabile in Rekordbox: punta ai file locali in libreria.
        # Una traccia senza file su disco non può stare in una playlist Rekordbox: la
        # escludiamo e segnaliamo il conteggio con un commento (le righe '#' non-direttiva
        # sono ignorate da Rekordbox).
        owned = [st.track for st in setlist.tracks if st.track.local_path]
        return PlainTextResponse(render_m3u8(owned, len(setlist.tracks)), media_type="audio/x-mpegurl")

    lines = [f"# {setlist.name}", ""]
    if setlist.global_explanation:
        lines += [setlist.global_explanation, ""]
    for st in setlist.tracks:
        t = st.track
        label = f"{t.artist or '?'} - {t.title or t.spotify_id or '?'}"
        meta = f"[{t.bpm:.0f} BPM, {t.camelot_key or '?'}]" if t.bpm else f"[{t.camelot_key or '?'}]"
        role = f"({st.role}) " if st.role else ""
        lines.append(f"{st.position:2d}. {role}{label} {meta}")
    return PlainTextResponse("\n".join(lines))


# --- Editing scaletta ---------------------------------------------------------


def _edit_error(exc: SetEditError) -> HTTPException:
    msg = str(exc).lower()
    if "non trovato" in msg or "non trovata" in msg:
        status = 404
    elif "gia'" in msg or "già" in msg:
        status = 409
    else:
        status = 422
    return api_error(status, "set_edit_error", f"Set edit error: {exc}", reason=str(exc))


@router.patch("/{setlist_id}", response_model=SetlistOut)
def rename(setlist_id: int, req: SetRenameRequest, db: Session = Depends(get_db)):
    try:
        return setlist_out(rename_set(db, setlist_id, req.name), get_language(db), db=db)
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.delete("/{setlist_id}", status_code=204)
def delete(setlist_id: int, db: Session = Depends(get_db)):
    try:
        delete_set(db, setlist_id)
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.delete("/{setlist_id}/tracks/{position}", response_model=SetlistOut)
def delete_track(setlist_id: int, position: int, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    try:
        return setlist_out(remove_track(db, setlist_id, position), get_language(db), db=db)
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks", response_model=SetlistOut)
def add(setlist_id: int, req: AddTrackRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    try:
        return setlist_out(add_track(db, setlist_id, req.track_id, req.position), get_language(db), db=db)
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks/{position}/move", response_model=SetlistOut)
def move(setlist_id: int, position: int, req: MoveTrackRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    try:
        if req.to is not None:
            setlist = move_track_to(db, setlist_id, position, req.to)
        else:
            setlist = move_track(db, setlist_id, position, req.direction)
        return setlist_out(setlist, get_language(db), db=db)
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks/{position}/replace", response_model=SetlistOut)
def replace(setlist_id: int, position: int, req: ReplaceTrackRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    try:
        return setlist_out(replace_track(db, setlist_id, position, req.track_id), get_language(db), db=db)
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/alternatives", response_model=AlternativesResponse)
def alternatives(setlist_id: int, req: AlternativesRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    _require_generated(setlist)
    try:
        alts = find_alternatives(db, setlist, req.position, req.mode, req.limit)
    except AlternativesError as exc:
        raise api_error(422, "alternatives_error", f"Alternatives error: {exc}",
                         reason=str(exc)) from exc
    # C1: stesso difetto di I3/M6 (commit 3eef90f) sull'ultimo payload rimasto
    # sui valori streaming — le Alternative di un set mostravano il genere
    # streaming mentre il resto dell'app mostra ormai quello effettivo.
    ft_map = file_tags_for_tracks(db, [a.track.id for a in alts])
    return AlternativesResponse(
        position=req.position,
        mode=req.mode,
        alternatives=[alternative_out(a, ft_map.get(a.track.id)) for a in alts],
    )
