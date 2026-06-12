"""Import della libreria: upsert tracce (idempotente su rekordbox_track_id) + report."""

import logging

from sqlalchemy.orm import Session

from app.models import BeatgridPoint, CuePoint, ImportReport, Track
from app.services.rekordbox_parser import ParsedTrack, parse_rekordbox_xml

logger = logging.getLogger(__name__)

# Dati DJ: Rekordbox e' la fonte di verita', sovrascrive sempre.
_DJ_FIELDS = (
    "spotify_id", "soundcloud_id", "source_type", "duration_seconds", "bpm",
    "tonality", "play_count", "rating", "comments", "location", "date_added",
)
# Metadata descrittivi: il re-import non deve cancellare i valori arricchiti
# da Spotify quando l'XML li ha vuoti (caso normale per le tracce Spotify).
_DESCRIPTIVE_FIELDS = ("title", "artist", "album", "genre", "year")


def _apply(track: Track, parsed: ParsedTrack) -> None:
    for f in _DJ_FIELDS:
        setattr(track, f, getattr(parsed, f))
    for f in _DESCRIPTIVE_FIELDS:
        value = getattr(parsed, f)
        if value is not None or getattr(track, f) is None:
            setattr(track, f, value)


def _build_stats(tracks: list[ParsedTrack]) -> dict:
    bpms = [t.bpm for t in tracks if t.bpm]
    key_distribution: dict[str, int] = {}
    for t in tracks:
        if t.tonality:
            key_distribution[t.tonality] = key_distribution.get(t.tonality, 0) + 1
    return {
        "total_tracks": len(tracks),
        "spotify_tracks": sum(1 for t in tracks if t.source_type == "spotify"),
        "soundcloud_tracks": sum(1 for t in tracks if t.source_type == "soundcloud"),
        "local_tracks": sum(1 for t in tracks if t.source_type == "local"),
        "with_bpm": len(bpms),
        "with_tonality": sum(1 for t in tracks if t.tonality),
        "with_cues": sum(1 for t in tracks if t.cues),
        "missing_title_or_artist": sum(1 for t in tracks if not t.title or not t.artist),
        "bpm_min": min(bpms) if bpms else None,
        "bpm_max": max(bpms) if bpms else None,
        "key_distribution": dict(sorted(key_distribution.items())),
    }


def import_rekordbox_xml(db: Session, content: bytes, filename: str | None = None) -> ImportReport:
    """Parsa l'XML, fa upsert delle tracce e salva un ImportReport."""
    result = parse_rekordbox_xml(content)

    created = updated = 0
    for parsed in result.tracks:
        existing = db.query(Track).filter(
            Track.rekordbox_track_id == parsed.rekordbox_track_id
        ).one_or_none()
        if existing is None:
            existing = Track(rekordbox_track_id=parsed.rekordbox_track_id)
            db.add(existing)
            created += 1
        else:
            # re-import: beatgrid e cue vengono ricreati da zero
            existing.beatgrid_points.clear()
            existing.cue_points.clear()
            updated += 1
        _apply(existing, parsed)
        for bg in parsed.beatgrid:
            existing.beatgrid_points.append(BeatgridPoint(
                start_seconds=bg.start_seconds, bpm=bg.bpm, meter=bg.meter, beat=bg.beat,
            ))
        for cue in parsed.cues:
            existing.cue_points.append(CuePoint(
                name=cue.name, type=cue.type, start_seconds=cue.start_seconds,
                num=cue.num, color=cue.color, comment=cue.comment,
            ))

    stats = _build_stats(result.tracks)
    stats["created"] = created
    stats["updated"] = updated

    report = ImportReport(filename=filename, stats=stats, errors=result.errors)
    db.add(report)
    db.commit()
    db.refresh(report)
    logger.info("Import completato: %s nuove, %s aggiornate, %s errori",
                created, updated, len(result.errors))
    return report
