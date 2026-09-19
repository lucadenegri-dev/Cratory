"""Conversione modelli ORM -> schemi Pydantic con campi derivati."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Setlist, Track
from app.repositories import FileTags, file_tags_for_tracks, get_playlist
from app.schemas import (
    ManualAlternativeOut,
    AlternativeOut,
    ManualBlockOut,
    ManualRowOut,
    ManualSetOut,
    ManualTransitionOut,
    SetDurationOut,
    SetlistOut,
    SetlistSummaryOut,
    SetlistTrackOut,
    TrackDetailOut,
    TrackOut,
    TrackPlaylistRef,
)
from app.services.manual_pairs import pair_compat
from app.services.manual_set import (
    can_redo, can_undo, pair_note_map, path_rows, set_duration,
)
from app.services.scoring import classify_transition, mixing_overview, mixing_tip


def _spotify_url(track: Track) -> str | None:
    return f"https://open.spotify.com/track/{track.spotify_id}" if track.spotify_id else None


def track_out(track: Track, file_tags: FileTags | None = None) -> TrackOut:
    ft = file_tags or FileTags()
    return TrackOut(
        id=track.id,
        spotify_id=track.spotify_id,
        soundcloud_id=track.soundcloud_id,
        source_type=track.source_type,
        platform=track.platform,
        title=track.title,
        artist=track.artist,
        album=ft.album if ft.album is not None else track.album,
        genre=ft.genre if ft.genre is not None else track.genre,
        year=ft.year if ft.year is not None else track.year,
        duration_seconds=track.duration_seconds,
        bpm=track.bpm,
        camelot_key=track.camelot_key,
        energy=track.energy,
        label=ft.label if ft.label is not None else track.label,
        status=track.status or "imported",
        url=track.url,
        isrc=track.isrc,
        playlists=[TrackPlaylistRef(id=p.id, name=p.name) for p in track.playlists],
        added_at=track.added_at,
        spotify_url=_spotify_url(track),
        album_art_url=track.album_art_url,
        has_local_file=bool(track.has_local_file),
        local_path=track.local_path,
        local_format=track.local_format,
        local_bitrate=track.local_bitrate,
        archived=bool(track.archived),
        rating=track.rating,
        last_download_outcome=track.last_download_outcome,
        last_download_reason=track.last_download_reason,
        last_download_path=track.last_download_path,
        primary_file_id=track.primary_file_id,
        genre_from_file=ft.genre is not None,
        album_from_file=ft.album is not None,
        label_from_file=ft.label is not None,
        year_from_file=ft.year is not None,
    )


def track_detail_out(track: Track, file_tags: FileTags | None = None) -> TrackDetailOut:
    ft = file_tags or FileTags()
    return TrackDetailOut(**track_out(track, file_tags).model_dump(),
                          file_artist=ft.artist, file_title=ft.title)


def _naive(dt: datetime) -> datetime:
    """Normalizza a naive UTC. Causa: `models.utcnow()` (default di
    created_at/updated_at) restituisce aware, ma le colonne `DateTime` sono
    naive - un giro DB le riporta senza tzinfo. Qui normalizziamo al confine
    del serializer; i serializer fuori dalla famiglia set (Track, Playlist,
    Organize, ...) hanno ancora lo stesso difetto a monte."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def setlist_out(setlist: Setlist, lang: str = "it", db: Session | None = None) -> SetlistOut:
    # F10: classifichiamo ogni transizione dal brano precedente (deterministico,
    # ricalcolato in lettura dai dati delle due tracce: nessuna colonna in DB).
    # M6: genere/album/label/anno effettivi (tag file) anche nel dettaglio set,
    # non solo in Library — una sola query in piu' per l'intero set (`db` e'
    # opzionale: i chiamanti che non lo passano restano col fallback streaming,
    # com'era prima).
    ft_map = file_tags_for_tracks(db, [st.track_id for st in setlist.tracks]) if db is not None else {}
    # I4: la classificazione del reset (classify_transition) deve leggere lo
    # STESSO genere effettivo mostrato in `track` qui sotto, non lo streaming
    # grezzo: altrimenti un set con quel brano "Progressive House" solo sul file
    # può etichettare come reset una transizione che non lo è (o viceversa).
    # D4: derivata da `ft_map` (già una query in blocco, riga sopra) invece di
    # un secondo giro di query — stessa espressione di `_EFFECTIVE_TAGS["genre"]`
    # (tag file se presente, altrimenti lo streaming), calcolata qui in Python.
    genre_map = ({st.track_id: ft_map.get(st.track_id, FileTags()).genre or st.track.genre
                 for st in setlist.tracks} if db is not None else None)
    items = []
    prev = None
    for st in setlist.tracks:
        # score=transition_score persistito: evita di ricomputare score_transition
        # per ogni riga del set (None su set storici -> fallback interno).
        cls = (classify_transition(prev, st.track, lang, score=st.transition_score, genre_map=genre_map)
               if prev is not None else None)
        items.append(SetlistTrackOut(
            position=st.position,
            role=st.role,
            track=track_out(st.track, ft_map.get(st.track_id)),
            transition_score=st.transition_score,
            transition_reason=st.transition_reason,
            transition_note=st.transition_note,
            risk_level=st.risk_level,
            transition_class=cls.label if cls else None,
            transition_class_reason=cls.reason if cls else None,
            mix_tip=mixing_tip(prev, st.track, lang) if prev is not None else None,
        ))
        prev = st.track
    total = sum(st.track.duration_seconds or 0 for st in setlist.tracks)
    return SetlistOut(
        id=setlist.id,
        name=setlist.name,
        target_duration_minutes=setlist.target_duration_minutes,
        start_bpm=setlist.start_bpm,
        end_bpm=setlist.end_bpm,
        strategy=setlist.strategy,
        prompt=setlist.prompt,
        global_explanation=setlist.global_explanation,
        generated_by=setlist.generated_by or "algorithmic",
        owned_only=bool(setlist.owned_only),
        validation=setlist.validation or {},
        mixing_overview=mixing_overview([st.track for st in setlist.tracks], lang),
        total_duration_seconds=total,
        created_at=_naive(setlist.created_at),
        tracks=items,
    )


def alternative_out(alt, file_tags: FileTags | None = None) -> AlternativeOut:
    return AlternativeOut(
        track=track_out(alt.track, file_tags),
        score_prev=alt.score_prev,
        score_next=alt.score_next,
        reason=alt.reason,
        risk_level=alt.risk_level,
    )


def setlist_summary_out(setlist: Setlist) -> SetlistSummaryOut:
    with_track = [st for st in setlist.tracks if st.track is not None]  # i varchi non contano
    return SetlistSummaryOut(
        id=setlist.id,
        name=setlist.name,
        kind=setlist.kind or "generated",
        strategy=setlist.strategy,
        target_duration_minutes=setlist.target_duration_minutes,
        track_count=len(with_track),
        total_duration_seconds=sum(st.track.duration_seconds or 0 for st in with_track),
        generated_by=setlist.generated_by or "algorithmic",
        created_at=_naive(setlist.created_at),
    )


def manual_set_out(setlist: Setlist, db: Session) -> ManualSetOut:
    """Documento del set manuale: blocchi in ordine, righe in ordine, riserva,
    candidate per riga, tag effettivi dei file come nel resto dell'app."""
    track_ids = [st.track_id for st in setlist.tracks if st.track_id is not None]
    track_ids += [a.track_id for st in setlist.tracks for a in st.alternatives]
    ft_map = file_tags_for_tracks(db, track_ids)

    def row_out(st) -> ManualRowOut:
        return ManualRowOut(
            id=st.id, block_id=st.block_id, position=st.position, slot_kind=st.slot_kind,
            play_bpm=st.play_bpm, planned_seconds=st.planned_seconds,
            track=track_out(st.track, ft_map.get(st.track_id)) if st.track is not None else None,
            note=st.note,
            alternatives=[ManualAlternativeOut(
                id=a.id, position=a.position, note=a.note,
                track=track_out(a.track, ft_map.get(a.track_id)),
            ) for a in sorted(st.alternatives, key=lambda a: a.position)],
        )

    blocks = []
    for block in sorted(setlist.blocks, key=lambda b: b.position):
        rows = sorted((st for st in setlist.tracks if st.block_id == block.id), key=lambda st: st.position)
        blocks.append(ManualBlockOut(
            id=block.id, name=block.name, placement=block.placement, position=block.position,
            rows=[row_out(st) for st in rows],
        ))
    # Conteggio e durata restano quelli del PERCORSO: ne' la riserva (senza
    # blocco) ne' il banco (blocchi `bench`) sono il set.
    nel_percorso = {b.id for b in setlist.blocks if b.placement == "main"}
    with_track = [st for st in setlist.tracks
                  if st.track is not None and st.block_id in nel_percorso]
    # I passaggi: solo fra righe con traccia e consecutive NEL PERCORSO. Un
    # varco aperto spezza la coppia (regola della spec), mentre il confine fra
    # due sequenze no: in cabina quelle due tracce si susseguono davvero.
    note_coppie = pair_note_map(setlist)
    transitions = []
    percorso = path_rows(setlist)
    for prima, dopo in zip(percorso, percorso[1:]):
        if prima.track is None or dopo.track is None:
            continue
        c = pair_compat(prima, dopo)
        transitions.append(ManualTransitionOut(
            from_row_id=prima.id, to_row_id=dopo.id,
            from_track_id=prima.track_id, to_track_id=dopo.track_id,
            bpm_from=c.bpm_from, bpm_to=c.bpm_to, bpm_percent=c.bpm_percent,
            halftime=c.halftime, key_from=c.key_from, key_to=c.key_to,
            key_relation=c.key_relation, score=c.score, missing=c.missing,
            note=note_coppie.get((prima.track_id, dopo.track_id)),
        ))
    playlist = get_playlist(db, setlist.source_playlist_id) if setlist.source_playlist_id else None
    return ManualSetOut(
        id=setlist.id, name=setlist.name, kind=setlist.kind, revision=setlist.revision,
        source_playlist_id=setlist.source_playlist_id,
        source_playlist_name=playlist.name if playlist is not None else None,
        notes=setlist.notes, blocks=blocks,
        reserve=[row_out(st) for st in sorted(
            (st for st in setlist.tracks if st.block_id is None), key=lambda st: st.position)],
        track_count=len(with_track),
        total_file_seconds=sum(st.track.duration_seconds or 0 for st in with_track),
        transitions=transitions,
        duration=SetDurationOut(**vars(set_duration(setlist))),
        can_undo=can_undo(setlist), can_redo=can_redo(setlist),
        created_at=_naive(setlist.created_at), updated_at=_naive(setlist.updated_at),
    )
