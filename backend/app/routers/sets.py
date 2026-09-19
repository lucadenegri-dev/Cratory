import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.repositories import (
    effective_genres_for_tracks,
    file_tags_for_tracks,
    get_playlist,
    get_setlist,
    list_setlists,
)
from app.schemas import (
    AlternativeChooseRequest,
    AlternativesAddRequest,
    BlockGroupRequest,
    BlockMoveRequest,
    BlockRenameRequest,
    FillGapRequest,
    HistoryStepRequest,
    PairNoteRequest,
    ManualSetCreate,
    SourceAddRequest,
    SourceOut,
    ManualSetOut,
    MaterialItemOut,
    MaterialOut,
    RowMoveRequest,
    RowPatchRequest,
    RowsInsertRequest,
    SetlistOut,
    SetlistSummaryOut,
    SetRenameRequest,
)
from app.serializers import manual_set_out, setlist_out, setlist_summary_out, track_out
from app.services.app_state import get_language
from app.services.manual_export import render_manual
from app.services.manual_fill import FillError
from app.services.manual_material import material_for, material_for_playlists
from app.services.manual_set import (
    AlternativeNotFound,
    BlockNotFound,
    NothingToRedo,
    NothingToUndo,
    PlaylistNotFound,
    add_alternatives,
    add_source,
    choose_alternative,
    remove_alternative,
    ManualSetError,
    ManualSetNotFound,
    ManualSetNotManual,
    RevisionConflict,
    RowNotFound,
    create_manual_set,
    insert_rows,
    UNSET,
    fill_gap,
    group_rows,
    load_manual_set,
    move_block,
    move_row,
    redo,
    remove_row,
    remove_source,
    rename_block,
    set_pair_note,
    split_block,
    undo,
    update_row,
)
from app.services.set_editor import (
    SetEditError,
    delete_set,
    rename_set,
)
from app.services.export_render import fmt_duration, render_m3u8
from app.services.scoring import classify_transition, mixing_tip, opening_track_label

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sets", tags=["sets"])


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
    if isinstance(exc, AlternativeNotFound):
        return api_error(404, "set_alternative_not_found", "Alternative not found")
    if isinstance(exc, FillError):
        return api_error(422, "set_fill_failed", f"Could not fill the gap: {exc}", reason=str(exc))
    if isinstance(exc, BlockNotFound):
        return api_error(404, "set_block_not_found", "Block not found")
    if isinstance(exc, NothingToUndo):
        return api_error(409, "set_nothing_to_undo", "Nothing to undo")
    if isinstance(exc, NothingToRedo):
        return api_error(409, "set_nothing_to_redo", "Nothing to redo")
    if isinstance(exc, PlaylistNotFound):
        return api_error(404, "playlist_not_found", "Playlist not found")
    return api_error(422, "manual_set_error", f"Manual set error: {exc}", reason=str(exc))


@router.post("/manual", response_model=ManualSetOut, status_code=201)
def create_manual(req: ManualSetCreate, db: Session = Depends(get_db)):
    """Set preparato a mano, vuoto, con la playlist di origine letta aggiornata."""
    try:
        return manual_set_out(create_manual_set(db, name=req.name, playlist_ids=req.playlist_ids), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.get("", response_model=list[SetlistSummaryOut])
def get_all(db: Session = Depends(get_db)):
    return [setlist_summary_out(s) for s in list_setlists(db)]


@router.get("/{setlist_id}/manual", response_model=ManualSetOut)
def get_manual(setlist_id: int, db: Session = Depends(get_db)):
    try:
        return manual_set_out(load_manual_set(db, setlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


def _material_out(db: Session, voci, playlist_ids: list[int]) -> MaterialOut:
    """Il payload del materiale, uno solo per il set e per la bozza: due copie
    quasi uguali divergono al primo campo nuovo."""
    ft_map = file_tags_for_tracks(db, [t.id for t, _, _, _ in voci])
    fonti = []
    for pid in playlist_ids:
        playlist = get_playlist(db, pid)
        fonti.append(SourceOut(playlist_id=pid,
                               name=playlist.name if playlist is not None else None))
    return MaterialOut(
        sources=fonti,
        items=[MaterialItemOut(track=track_out(t, ft_map.get(t.id)), in_set=in_set,
                               from_playlist=fp, in_reserve=in_res)
               for t, in_set, fp, in_res in voci],
    )


# ATTENZIONE all'ordine: questa rotta statica va dichiarata PRIMA di qualunque
# `GET /{qualcosa}` che potrebbe catturarla. Oggi non ce n'e' nessuna, ma chi ne
# aggiunge una domani la romperebbe in silenzio.
@router.get("/material", response_model=MaterialOut)
def draft_material(playlist_ids: list[int] = Query(default=[]),
                   q: str | None = Query(default=None, max_length=200),
                   owned: bool = False, db: Session = Depends(get_db)):
    """Il materiale di una BOZZA: il set non esiste ancora (non si crea finche'
    non ci si mette dentro qualcosa), quindi si chiede per playlist."""
    return _material_out(db, material_for_playlists(db, playlist_ids, q=q, owned=owned),
                         playlist_ids)


@router.get("/{setlist_id}/material", response_model=MaterialOut)
def get_material(setlist_id: int, q: str | None = Query(default=None, max_length=200),
                 owned: bool = False, unused: bool = False, reserved: bool = False,
                 db: Session = Depends(get_db)):
    """Playlist di origine aggiornata + tracce nel set + (con q) ricerca in libreria."""
    try:
        setlist = load_manual_set(db, setlist_id)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
    items = material_for(db, setlist, q=q, owned=owned, unused=unused, reserved=reserved)
    return _material_out(db, items, [src.playlist_id for src in setlist.sources])


@router.post("/{setlist_id}/rows", response_model=ManualSetOut)
def rows_insert(setlist_id: int, req: RowsInsertRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(insert_rows(
            db, setlist_id, expected_revision=req.expected_revision,
            track_ids=req.track_ids, gap=req.gap, after_row_id=req.after_row_id,
            reserve=req.reserve), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/move", response_model=ManualSetOut)
def rows_move(setlist_id: int, row_id: int, req: RowMoveRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(move_row(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            position=req.position, to_reserve=req.to_reserve), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.patch("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_patch(setlist_id: int, row_id: int, req: RowPatchRequest, db: Session = Depends(get_db)):
    """Aggiorna i soli campi MANDATI: un campo assente non e' un campo da azzerare."""
    inviati = req.model_fields_set
    try:
        return manual_set_out(update_row(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            note=req.note if "note" in inviati else UNSET,
            play_bpm=req.play_bpm if "play_bpm" in inviati else UNSET,
            planned_seconds=req.planned_seconds if "planned_seconds" in inviati else UNSET), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_delete(setlist_id: int, row_id: int, expected_revision: int = Query(ge=0),
                db: Session = Depends(get_db)):
    try:
        return manual_set_out(remove_row(db, setlist_id, row_id, expected_revision=expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/alternatives", response_model=ManualSetOut)
def alternatives_add(setlist_id: int, row_id: int, req: AlternativesAddRequest,
                     db: Session = Depends(get_db)):
    """Candidate su una riga: quelle che il DJ tiene li' accanto, non quelle
    calcolate dal generatore (vedi POST /{id}/alternatives, per i set generati)."""
    try:
        return manual_set_out(add_alternatives(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            track_ids=req.track_ids), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/rows/{row_id}/alternatives/{alt_id}", response_model=ManualSetOut)
def alternatives_remove(setlist_id: int, row_id: int, alt_id: int,
                        expected_revision: int = Query(ge=0), db: Session = Depends(get_db)):
    try:
        return manual_set_out(remove_alternative(
            db, setlist_id, row_id, alt_id, expected_revision=expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/alternatives/{alt_id}/choose",
             response_model=ManualSetOut)
def alternatives_choose(setlist_id: int, row_id: int, alt_id: int,
                        req: AlternativeChooseRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(choose_alternative(
            db, setlist_id, row_id, alt_id, expected_revision=req.expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


# --- Sequenze, banco, annulla e ripeti (tappa 3) -------------------------------


@router.post("/{setlist_id}/blocks", response_model=ManualSetOut)
def blocks_group(setlist_id: int, req: BlockGroupRequest, db: Session = Depends(get_db)):
    """Raggruppa righe contigue in una sequenza: l'ordine del percorso non
    cambia, cambia come e' diviso."""
    try:
        return manual_set_out(group_rows(
            db, setlist_id, expected_revision=req.expected_revision,
            row_ids=req.row_ids, name=req.name), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.patch("/{setlist_id}/blocks/{block_id}", response_model=ManualSetOut)
def blocks_rename(setlist_id: int, block_id: int, req: BlockRenameRequest,
                  db: Session = Depends(get_db)):
    """Nome della sequenza; vuoto la lascia senza nome."""
    try:
        return manual_set_out(rename_block(
            db, setlist_id, block_id, expected_revision=req.expected_revision, name=req.name), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/blocks/{block_id}/move", response_model=ManualSetOut)
def blocks_move(setlist_id: int, block_id: int, req: BlockMoveRequest,
                db: Session = Depends(get_db)):
    """Sposta la sequenza intera, nel percorso o sul banco: l'ordine interno
    non si tocca mai."""
    try:
        return manual_set_out(move_block(
            db, setlist_id, block_id, expected_revision=req.expected_revision,
            position=req.position, to_bench=req.to_bench), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/blocks/{block_id}/split", response_model=ManualSetOut)
def blocks_split(setlist_id: int, block_id: int, req: HistoryStepRequest,
                 db: Session = Depends(get_db)):
    """Scioglie la sequenza: le righe restano nel percorso, nell'ordine."""
    try:
        return manual_set_out(split_block(
            db, setlist_id, block_id, expected_revision=req.expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/undo", response_model=ManualSetOut)
def history_undo(setlist_id: int, req: HistoryStepRequest, db: Session = Depends(get_db)):
    """Torna allo stato precedente. `revision` cresce anche qui: annullare e'
    una modifica come le altre per chi sta guardando da un'altra finestra."""
    try:
        return manual_set_out(undo(db, setlist_id, expected_revision=req.expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/redo", response_model=ManualSetOut)
def history_redo(setlist_id: int, req: HistoryStepRequest, db: Session = Depends(get_db)):
    """Rimette quello che si era annullato, finche' non si fa altro."""
    try:
        return manual_set_out(redo(db, setlist_id, expected_revision=req.expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/fill-gap", response_model=ManualSetOut)
def rows_fill_gap(setlist_id: int, row_id: int, req: FillGapRequest,
                  db: Session = Depends(get_db)):
    """Il generatore propone `count` tracce per quel varco e le inserisce come
    righe normali: si spostano, si cambiano, si cancellano, e un annulla riapre
    il varco. Deterministico, nessuna chiamata AI."""
    try:
        return manual_set_out(fill_gap(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            count=req.count), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/sources", response_model=ManualSetOut)
def sources_add(setlist_id: int, req: SourceAddRequest, db: Session = Depends(get_db)):
    """Aggiunge una playlist alle origini del materiale."""
    try:
        return manual_set_out(add_source(
            db, setlist_id, expected_revision=req.expected_revision,
            playlist_id=req.playlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/sources/{playlist_id}", response_model=ManualSetOut)
def sources_remove(setlist_id: int, playlist_id: int, expected_revision: int = Query(ge=0),
                   db: Session = Depends(get_db)):
    """Toglie un'origine. Il percorso non si tocca: una traccia gia' scelta e'
    una decisione presa."""
    try:
        return manual_set_out(remove_source(
            db, setlist_id, expected_revision=expected_revision,
            playlist_id=playlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.put("/{setlist_id}/pair-notes", response_model=ManualSetOut)
def pair_notes_put(setlist_id: int, req: PairNoteRequest, db: Session = Depends(get_db)):
    """Appunto su un passaggio, legato alle due TRACCE: sopravvive a chi cambia
    idea sul percorso. Testo vuoto = cancella."""
    try:
        return manual_set_out(set_pair_note(
            db, setlist_id, expected_revision=req.expected_revision,
            from_track_id=req.from_track_id, to_track_id=req.to_track_id,
            note=req.note), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/export", response_class=PlainTextResponse)
def export(
    setlist_id: int,
    format: str = Query(default="text", pattern="^(text|csv|markdown|m3u8|prep|reserve)$"),
    db: Session = Depends(get_db),
):
    """Export del set: testo, CSV, Markdown o M3U8 (playlist Rekordbox). Export playlist Spotify: endpoint dedicato.

    I set preparati a mano leggono il PERCORSO RISOLTO e hanno in piu' la scheda
    di preparazione (`prep`) e l'elenco delle riserve (`reserve`)."""
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    lang = get_language(db)
    if setlist.kind == "manual":
        contenuto, media = render_manual(setlist, format, lang)
        return PlainTextResponse(contenuto, media_type=media)
    if format in ("prep", "reserve"):
        raise api_error(422, "set_format_not_available",
                        "This format belongs to a hand-prepared set")
    # Un set generato ancora in archivio si esporta ancora: e' l'unico modo di
    # portarselo via prima di cancellarlo, ora che non ha piu' una pagina.
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


