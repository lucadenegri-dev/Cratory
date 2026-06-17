import csv
import io
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal, get_db
from app.integrations.llm import LLMError, LLMNotConfigured, get_llm_client, llm_configured
from app.repositories import get_setlist, list_setlists
from app.schemas import (
    AlternativesRequest,
    AlternativesResponse,
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
from app.services.set_editor import (
    SetEditError,
    delete_set,
    move_track,
    remove_track,
    rename_set,
    replace_track,
)
from app.services.scoring import classify_transition
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
            _gen_state["phase"] = "Costruisco il set"
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


@router.post("/generate-async")
def generate_async(req: SetGenerationRequest):
    """Avvia la generazione in background e ritorna subito. Seguire /generate-status."""
    use_ai = _should_use_ai(req)
    if use_ai and not llm_configured():
        raise HTTPException(status_code=409, detail="AI non configurata (AI_API_KEY mancante).")
    with _gen_lock:
        if _gen_state["status"] == "running":
            return {"status": "running", "phase": _gen_state["phase"], "using_ai": _gen_state["using_ai"]}
        _gen_state.update(status="running", phase=None, using_ai=use_ai, setlist_id=None,
                          error=None, started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    threading.Thread(target=_run_generation, args=(req, use_ai), daemon=True).start()
    return {"status": "running", "phase": None, "using_ai": use_ai}


@router.get("/generate-status")
def generate_status():
    return dict(_gen_state)


@router.post("/generate", response_model=SetlistOut)
def generate(req: SetGenerationRequest, db: Session = Depends(get_db)):
    if _should_use_ai(req):
        try:
            setlist = generate_ai_set(db, req, get_llm_client(_model_for(req)))
        except LLMNotConfigured as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (AIAgentError, LLMError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return setlist_out(setlist)
    try:
        setlist = generate_set(db, req)
    except SetGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return setlist_out(setlist)


@router.get("", response_model=list[SetlistSummaryOut])
def get_all(db: Session = Depends(get_db)):
    return [setlist_summary_out(s) for s in list_setlists(db)]


@router.get("/{setlist_id}", response_model=SetlistOut)
def get_one(setlist_id: int, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise HTTPException(status_code=404, detail="Set non trovato")
    return setlist_out(setlist)


def _fmt_dur(seconds: int | None) -> str:
    if not seconds:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


@router.post("/{setlist_id}/export", response_class=PlainTextResponse)
def export(
    setlist_id: int,
    format: str = Query(default="text", pattern="^(text|csv|markdown)$"),
    db: Session = Depends(get_db),
):
    """Export del set: testo, CSV o Markdown. Export playlist Spotify: endpoint dedicato."""
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise HTTPException(status_code=404, detail="Set non trovato")

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["position", "role", "title", "artist", "bpm", "key", "duration_seconds",
                         "source", "spotify_id", "url", "transition_score", "risk_level",
                         "transition_class"])
        prev = None
        for st in setlist.tracks:
            t = st.track
            cls = classify_transition(prev, t).label if prev is not None else ""
            writer.writerow([st.position, st.role or "", t.title or "", t.artist or "", t.bpm or "",
                             t.camelot_key or "", t.duration_seconds or "", t.source_type,
                             t.spotify_id or "", t.url or "", st.transition_score or "", st.risk_level or "",
                             cls])
            prev = t
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    if format == "markdown":
        md = [f"# {setlist.name}", ""]
        if setlist.global_explanation:
            md += [setlist.global_explanation, ""]
        md += ["| # | Ruolo | Traccia | BPM | Key | Durata | Transizione |",
               "|--:|---|---|--:|---|--:|---|"]
        for st in setlist.tracks:
            t = st.track
            label = f"{t.artist or '?'} — {t.title or t.spotify_id or '?'}"
            note = (st.transition_note or st.transition_reason or "").replace("|", "/").replace("\n", " ")
            md.append(
                f"| {st.position} | {st.role or ''} | {label} | "
                f"{t.bpm:.0f} | {t.camelot_key or '?'} | {_fmt_dur(t.duration_seconds)} | {note} |"
                if t.bpm else
                f"| {st.position} | {st.role or ''} | {label} | — | "
                f"{t.camelot_key or '?'} | {_fmt_dur(t.duration_seconds)} | {note} |"
            )
        return PlainTextResponse("\n".join(md), media_type="text/markdown")

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
    status = 404 if "non trovato" in str(exc).lower() else 422
    return HTTPException(status_code=status, detail=str(exc))


@router.patch("/{setlist_id}", response_model=SetlistOut)
def rename(setlist_id: int, req: SetRenameRequest, db: Session = Depends(get_db)):
    try:
        return setlist_out(rename_set(db, setlist_id, req.name))
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
        return setlist_out(remove_track(db, setlist_id, position))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks/{position}/move", response_model=SetlistOut)
def move(setlist_id: int, position: int, req: MoveTrackRequest, db: Session = Depends(get_db)):
    try:
        return setlist_out(move_track(db, setlist_id, position, req.direction))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/tracks/{position}/replace", response_model=SetlistOut)
def replace(setlist_id: int, position: int, req: ReplaceTrackRequest, db: Session = Depends(get_db)):
    try:
        return setlist_out(replace_track(db, setlist_id, position, req.track_id))
    except SetEditError as exc:
        raise _edit_error(exc) from exc


@router.post("/{setlist_id}/alternatives", response_model=AlternativesResponse)
def alternatives(setlist_id: int, req: AlternativesRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise HTTPException(status_code=404, detail="Set non trovato")
    try:
        alts = find_alternatives(db, setlist, req.position, req.mode, req.limit)
    except AlternativesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AlternativesResponse(
        position=req.position,
        mode=req.mode,
        alternatives=[alternative_out(a) for a in alts],
    )
