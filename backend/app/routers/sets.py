import csv
import io
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_errors import api_error
from app.db import SessionLocal, get_db
from app.integrations.llm import LLMError, LLMNotConfigured, get_llm_client, llm_configured
from app.repositories import get_setlist, list_setlists
from app.schemas import (
    AddTrackRequest,
    AlternativesRequest,
    AlternativesResponse,
    GenerateAsyncStartOut,
    GenerateStatusOut,
    MoveTrackRequest,
    ReplaceTrackRequest,
    SetGenerationRequest,
    SetlistOut,
    SetlistSummaryOut,
    SetRenameRequest,
)
from app.serializers import alternative_out, setlist_out, setlist_summary_out
from app.services.ai_agent import AIAgentError, generate_ai_set
from app.services.alternatives import AlternativesError, find_alternatives
from app.services.app_state import get_language
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


def _model_for(req: SetGenerationRequest) -> str | None:
    """Modello da usare: in creative, se impostato, usa AI_MODEL_CREATIVE (più capace)."""
    if req.mode == "creative" and settings.ai_model_creative:
        return settings.ai_model_creative
    return None  # None = default (AI_MODEL / DEFAULT_MODEL)


# Fase mostrata durante la generazione deterministica (non-AI); le fasi del
# path AI sono già bilingui in ai_agent.py (_PHASES).
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
            setlist = generate_ai_set(
                db, req, get_llm_client(_model_for(req)),
                on_phase=lambda p: _gen_state.update(phase=p),
            )
        else:
            lang = get_language(db)
            _gen_state["phase"] = _BUILDING_SET_PHASE.get(lang, _BUILDING_SET_PHASE["it"])
            setlist = generate_set(db, req)
        _gen_state.update(status="done", setlist_id=setlist.id, phase=None)
        logger.info("Job generazione completato: set %s (%s)", setlist.id, setlist.generated_by)
    except (AIAgentError, LLMError, LLMNotConfigured, SetGenerationError) as exc:
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
        raise api_error(409, "ai_not_configured", "AI not configured: AI_API_KEY missing.",
                         reason="AI_API_KEY mancante")
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


@router.post("/generate", response_model=SetlistOut)
def generate(req: SetGenerationRequest, db: Session = Depends(get_db)):
    lang = get_language(db)
    if _should_use_ai(req):
        try:
            setlist = generate_ai_set(db, req, get_llm_client(_model_for(req)))
        except LLMNotConfigured as exc:
            raise api_error(409, "ai_not_configured", f"AI not configured: {exc}",
                             reason=str(exc)) from exc
        except (AIAgentError, LLMError) as exc:
            raise api_error(422, "set_ai_generation_failed", f"AI set generation failed: {exc}",
                             reason=str(exc)) from exc
        return setlist_out(setlist, lang)
    try:
        setlist = generate_set(db, req)
    except SetGenerationError as exc:
        raise api_error(422, "set_generation_failed", f"Set generation failed: {exc}",
                         reason=str(exc)) from exc
    return setlist_out(setlist, lang)


@router.get("", response_model=list[SetlistSummaryOut])
def get_all(db: Session = Depends(get_db)):
    return [setlist_summary_out(s) for s in list_setlists(db)]


@router.get("/{setlist_id}", response_model=SetlistOut)
def get_one(setlist_id: int, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    return setlist_out(setlist, get_language(db))


def _fmt_dur(seconds: int | None) -> str:
    if not seconds:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


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
    lang = get_language(db)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["position", "role", "title", "artist", "bpm", "key", "duration_seconds",
                         "source", "spotify_id", "url", "transition_score", "risk_level",
                         "transition_class", "local_path"])
        prev = None
        for st in setlist.tracks:
            t = st.track
            cls = (classify_transition(prev, t, lang, score=st.transition_score).label
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
                f"{t.bpm:.0f} | {t.camelot_key or '?'} | {_fmt_dur(t.duration_seconds)} | {note} |"
                if t.bpm else
                f"| {st.position} | {st.role or ''} | {label} | — | "
                f"{t.camelot_key or '?'} | {_fmt_dur(t.duration_seconds)} | {note} |"
            )
        return PlainTextResponse("\n".join(md), media_type="text/markdown")

    if format == "m3u8":
        # Playlist importabile in Rekordbox: punta ai file locali in libreria.
        # Una traccia senza file su disco non può stare in una playlist Rekordbox: la
        # escludiamo e segnaliamo il conteggio con un commento (le righe '#' non-direttiva
        # sono ignorate da Rekordbox).
        owned = [st for st in setlist.tracks if st.track.local_path]
        skipped = len(setlist.tracks) - len(owned)
        m3u = ["#EXTM3U"]
        if skipped:
            m3u.append(f"# {skipped} tracce senza file locale non incluse")
        for st in owned:
            t = st.track
            secs = int(t.duration_seconds) if t.duration_seconds else -1
            m3u.append(f"#EXTINF:{secs},{t.artist or '?'} — {t.title or t.spotify_id or '?'}")
            m3u.append(t.local_path)
        return PlainTextResponse("\n".join(m3u), media_type="audio/x-mpegurl")

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
        return setlist_out(rename_set(db, setlist_id, req.name), get_language(db))
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
    try:
        return setlist_out(remove_track(db, setlist_id, position), get_language(db))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks", response_model=SetlistOut)
def add(setlist_id: int, req: AddTrackRequest, db: Session = Depends(get_db)):
    try:
        return setlist_out(add_track(db, setlist_id, req.track_id, req.position), get_language(db))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks/{position}/move", response_model=SetlistOut)
def move(setlist_id: int, position: int, req: MoveTrackRequest, db: Session = Depends(get_db)):
    try:
        if req.to is not None:
            setlist = move_track_to(db, setlist_id, position, req.to)
        else:
            setlist = move_track(db, setlist_id, position, req.direction)
        return setlist_out(setlist, get_language(db))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks/{position}/replace", response_model=SetlistOut)
def replace(setlist_id: int, position: int, req: ReplaceTrackRequest, db: Session = Depends(get_db)):
    try:
        return setlist_out(replace_track(db, setlist_id, position, req.track_id), get_language(db))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/alternatives", response_model=AlternativesResponse)
def alternatives(setlist_id: int, req: AlternativesRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    try:
        alts = find_alternatives(db, setlist, req.position, req.mode, req.limit)
    except AlternativesError as exc:
        raise api_error(422, "alternatives_error", f"Alternatives error: {exc}",
                         reason=str(exc)) from exc
    return AlternativesResponse(
        position=req.position,
        mode=req.mode,
        alternatives=[alternative_out(a) for a in alts],
    )
