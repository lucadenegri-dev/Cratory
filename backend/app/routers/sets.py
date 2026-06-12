import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import get_setlist, list_setlists
from app.schemas import SetGenerationRequest, SetlistOut, SetlistSummaryOut
from app.serializers import setlist_out, setlist_summary_out
from app.services.set_generator import SetGenerationError, generate_set

router = APIRouter(prefix="/api/sets", tags=["sets"])


@router.post("/generate", response_model=SetlistOut)
def generate(req: SetGenerationRequest, db: Session = Depends(get_db)):
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


@router.post("/{setlist_id}/export", response_class=PlainTextResponse)
def export(
    setlist_id: int,
    format: str = Query(default="text", pattern="^(text|csv)$"),
    db: Session = Depends(get_db),
):
    """Export del set in testo o CSV. Export playlist Spotify: MVP 2."""
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise HTTPException(status_code=404, detail="Set non trovato")

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["position", "title", "artist", "bpm", "key", "duration_seconds",
                         "source", "spotify_id", "transition_score", "risk_level"])
        for st in setlist.tracks:
            t = st.track
            writer.writerow([st.position, t.title or "", t.artist or "", t.bpm or "",
                             t.tonality or "", t.duration_seconds or "", t.source_type,
                             t.spotify_id or "", st.transition_score or "", st.risk_level or ""])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    lines = [f"# {setlist.name}", ""]
    if setlist.global_explanation:
        lines += [setlist.global_explanation, ""]
    for st in setlist.tracks:
        t = st.track
        label = f"{t.artist or '?'} - {t.title or t.spotify_id or t.rekordbox_track_id}"
        meta = f"[{t.bpm:.0f} BPM, {t.tonality or '?'}]" if t.bpm else f"[{t.tonality or '?'}]"
        lines.append(f"{st.position:2d}. {label} {meta}")
    return PlainTextResponse("\n".join(lines))
