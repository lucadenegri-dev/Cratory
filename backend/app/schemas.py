"""Schemi Pydantic per request/response API."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rekordbox_track_id: str
    spotify_id: str | None = None
    soundcloud_id: str | None = None
    source_type: str
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
    date_added: date | None = None
    cue_count: int = 0
    has_beatgrid: bool = False
    spotify_url: str | None = None
    album_art_url: str | None = None
    enriched: bool = False


class TrackListOut(BaseModel):
    total: int
    items: list[TrackOut]


class CuePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    type: str | None = None
    start_seconds: float
    num: int | None = None


class TrackDetailOut(TrackOut):
    comments: str | None = None
    location: str | None = None
    cue_points: list[CuePointOut] = []
    beatgrid_bpms: list[float] = []


class ImportReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str | None = None
    stats: dict
    errors: list
    created_at: datetime


class TransitionScoreOut(BaseModel):
    score: int = Field(ge=0, le=100)
    technical_reasons: list[str] = []
    warnings: list[str] = []


class TransitionScoreRequest(BaseModel):
    from_track_id: int
    to_track_id: int


class TransitionCandidateOut(BaseModel):
    track: TrackOut
    score: TransitionScoreOut


class SetGenerationRequest(BaseModel):
    name: str | None = None
    target_duration_minutes: int = Field(default=60, ge=10, le=300)
    start_bpm: float | None = None
    end_bpm: float | None = None
    seed_artists: list[str] = []
    genre: str | None = None
    preferred_keys: list[str] = []
    strategy: str = "smooth"  # smooth|progressive|contrast|experimental|peak_time|warm_up|closing
    max_tracks_per_artist: int = Field(default=2, ge=1, le=10)
    sources: list[str] = []  # vuoto = tutte; valori: spotify|soundcloud|local
    prefer_harmonic: bool = True
    prefer_progressive_bpm: bool = True
    allow_sharp_changes: bool = False
    avoid_short_tracks: bool = True
    avoid_overplayed: bool = False
    prompt: str | None = None  # prompt libero: usato dall'AI agent in MVP 3
    use_ai: bool | None = None  # None = auto (AI se configurata e c'e' un prompt)


class AITrackChoice(BaseModel):
    """Una traccia scelta dall'AI Set Agent (output validato con Pydantic)."""

    position: int
    track_id: int
    reason: str = ""
    transition_note: str = ""
    risk_level: str = "medium"  # low | medium | high


class AISetResponse(BaseModel):
    """Output dell'AI Set Agent prima della validazione deterministica."""

    set_title: str = ""
    global_explanation: str = ""
    tracks: list[AITrackChoice] = []
    critical_points: list[str] = []
    alternative_directions: list[str] = []
    missing_library_suggestions: list[str] = []


class SetlistTrackOut(BaseModel):
    position: int
    track: TrackOut
    transition_score: float | None = None
    transition_reason: str | None = None
    ai_reason: str | None = None
    risk_level: str | None = None


class SetlistOut(BaseModel):
    id: int
    name: str
    target_duration_minutes: int | None = None
    start_bpm: float | None = None
    end_bpm: float | None = None
    strategy: str | None = None
    prompt: str | None = None
    global_explanation: str | None = None
    generated_by: str = "algorithmic"
    validation: dict = {}
    total_duration_seconds: int = 0
    created_at: datetime
    tracks: list[SetlistTrackOut] = []


class SetlistSummaryOut(BaseModel):
    id: int
    name: str
    strategy: str | None = None
    target_duration_minutes: int | None = None
    track_count: int = 0
    created_at: datetime


class LibraryStatsOut(BaseModel):
    total_tracks: int
    by_source: dict[str, int]
    with_bpm: int
    with_tonality: int
    with_cues: int
    missing_metadata: int
    bpm_min: float | None = None
    bpm_max: float | None = None
    key_distribution: dict[str, int]
    last_import: ImportReportOut | None = None
