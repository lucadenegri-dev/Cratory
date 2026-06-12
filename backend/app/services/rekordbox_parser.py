"""Parser dell'export XML di Rekordbox (nodo COLLECTION).

Pattern Location osservati nel file reale (Rekordbox 7.2.14):
- Spotify:    file://localhostspotify:track:<ID>
- SoundCloud: file://localhostsoundcloud:tracks:<ID numerico>
- Locale:     file://localhost/Users/... (URL-encoded)
"""

from dataclasses import dataclass, field
from datetime import date

from lxml import etree

SPOTIFY_PREFIX = "file://localhostspotify:track:"
SOUNDCLOUD_PREFIX = "file://localhostsoundcloud:tracks:"


@dataclass
class ParsedBeatgridPoint:
    start_seconds: float
    bpm: float
    meter: str | None
    beat: int | None


@dataclass
class ParsedCuePoint:
    name: str | None
    type: str | None
    start_seconds: float
    num: int | None
    color: str | None
    comment: str | None


@dataclass
class ParsedTrack:
    rekordbox_track_id: str
    source_type: str
    spotify_id: str | None = None
    soundcloud_id: str | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    year: int | None = None
    duration_seconds: int | None = None
    bpm: float | None = None
    tonality: str | None = None
    play_count: int = 0
    rating: int | None = None
    comments: str | None = None
    location: str | None = None
    date_added: date | None = None
    beatgrid: list[ParsedBeatgridPoint] = field(default_factory=list)
    cues: list[ParsedCuePoint] = field(default_factory=list)


@dataclass
class ParseResult:
    tracks: list[ParsedTrack] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _to_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def detect_source(location: str | None) -> tuple[str, str | None, str | None]:
    """Ritorna (source_type, spotify_id, soundcloud_id) dal campo Location."""
    if location and location.startswith(SPOTIFY_PREFIX):
        return "spotify", location.removeprefix(SPOTIFY_PREFIX) or None, None
    if location and location.startswith(SOUNDCLOUD_PREFIX):
        return "soundcloud", None, location.removeprefix(SOUNDCLOUD_PREFIX) or None
    return "local", None, None


def _parse_track(node: etree._Element) -> ParsedTrack:
    location = _clean(node.get("Location"))
    source_type, spotify_id, soundcloud_id = detect_source(location)

    year = _to_int(node.get("Year"))
    bpm = _to_float(node.get("AverageBpm"))

    track = ParsedTrack(
        rekordbox_track_id=node.get("TrackID", "").strip(),
        source_type=source_type,
        spotify_id=spotify_id,
        soundcloud_id=soundcloud_id,
        title=_clean(node.get("Name")),
        artist=_clean(node.get("Artist")),
        album=_clean(node.get("Album")),
        genre=_clean(node.get("Genre")),
        year=year if year else None,  # Year="0" -> None
        duration_seconds=_to_int(node.get("TotalTime")),
        bpm=bpm if bpm else None,  # AverageBpm="0.00" -> None
        tonality=_clean(node.get("Tonality")),
        play_count=_to_int(node.get("PlayCount")) or 0,
        rating=_to_int(node.get("Rating")),
        comments=_clean(node.get("Comments")),
        location=location,
        date_added=_to_date(node.get("DateAdded")),
    )

    for tempo in node.findall("TEMPO"):
        start = _to_float(tempo.get("Inizio"))
        t_bpm = _to_float(tempo.get("Bpm"))
        if start is None or t_bpm is None:
            continue
        track.beatgrid.append(
            ParsedBeatgridPoint(
                start_seconds=start,
                bpm=t_bpm,
                meter=_clean(tempo.get("Metro")),
                beat=_to_int(tempo.get("Battito")),
            )
        )

    for mark in node.findall("POSITION_MARK"):
        start = _to_float(mark.get("Start"))
        if start is None:
            continue
        track.cues.append(
            ParsedCuePoint(
                name=_clean(mark.get("Name")),
                type=_clean(mark.get("Type")),
                start_seconds=start,
                num=_to_int(mark.get("Num")),
                color=None,
                comment=None,
            )
        )

    return track


def parse_rekordbox_xml(content: bytes) -> ParseResult:
    """Parsa il contenuto di un export XML Rekordbox e ritorna tracce + errori."""
    result = ParseResult()
    try:
        root = etree.fromstring(content)
    except etree.XMLSyntaxError as exc:
        result.errors.append(f"XML non valido: {exc}")
        return result

    collection = root.find("COLLECTION")
    if collection is None:
        result.errors.append("Nodo COLLECTION non trovato nel file XML")
        return result

    for node in collection.findall("TRACK"):
        track_id = node.get("TrackID")
        try:
            parsed = _parse_track(node)
            if not parsed.rekordbox_track_id:
                result.errors.append("Traccia senza TrackID ignorata")
                continue
            result.tracks.append(parsed)
        except Exception as exc:  # noqa: BLE001 - una traccia rotta non blocca l'import
            result.errors.append(f"Errore parsing traccia TrackID={track_id}: {exc}")

    return result
