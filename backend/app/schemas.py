"""Schemi Pydantic per request/response API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    spotify_id: str | None = None
    soundcloud_id: str | None = None
    source_type: str
    platform: str | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    genre_secondary: str | None = None
    year: int | None = None
    duration_seconds: int | None = None
    bpm: float | None = None
    camelot_key: str | None = None
    mood: str | None = None
    energy: int | None = None
    danceability: int | None = None
    vocalness: int | None = None
    label: str | None = None
    status: str = "imported"
    url: str | None = None
    isrc: str | None = None
    playlist_id: int | None = None
    playlist_name: str | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    enriched: bool = False
    enrichment_source: str | None = None
    enrichment_confidence: int | None = None


class TrackListOut(BaseModel):
    total: int
    items: list[TrackOut]


class TrackDetailOut(TrackOut):
    """Dettaglio traccia: oggi coincide con TrackOut (niente cue/beatgrid Rekordbox)."""


class TrackUpdateIn(BaseModel):
    """Modifica manuale di una traccia.

    Solo i campi presenti nel payload vengono toccati (PATCH parziale): un valore
    `null` azzera il campo, un campo assente resta invariato. I valori inseriti a
    mano hanno la precedenza sull'enrichment automatico (l'utente sa cosa scrive):
    se si tocca una feature musicale la fonte diventa `manual` con confidenza piena.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    genre_secondary: str | None = None
    year: int | None = Field(default=None, ge=0, le=3000)
    duration_seconds: int | None = Field(default=None, ge=0)
    bpm: float | None = Field(default=None, gt=0, le=400)
    camelot_key: str | None = None
    mood: str | None = None
    energy: int | None = Field(default=None, ge=0, le=100)
    danceability: int | None = Field(default=None, ge=0, le=100)
    vocalness: int | None = Field(default=None, ge=0, le=100)
    label: str | None = None


class TransitionScoreOut(BaseModel):
    score: int = Field(ge=0, le=100)
    technical_reasons: list[str] = []
    warnings: list[str] = []
    # F10: classificazione semantica (technically_safe | creative_risk | good_reset)
    classification: str | None = None
    classification_label: str | None = None
    classification_reason: str | None = None


class TransitionScoreRequest(BaseModel):
    from_track_id: int
    to_track_id: int


class TransitionCandidateOut(BaseModel):
    track: TrackOut
    score: TransitionScoreOut


class SetGenerationRequest(BaseModel):
    name: str | None = None
    # se valorizzato, il set parte SOLO dalle tracce di questa playlist importata
    playlist_id: int | None = None
    target_duration_minutes: int = Field(default=60, ge=10, le=300)
    start_bpm: float | None = None
    end_bpm: float | None = None
    # progressione di energia (0-100) e mood lungo il set (nuovo_progetto.md sez. 4)
    start_energy: int | None = Field(default=None, ge=0, le=100)
    end_energy: int | None = Field(default=None, ge=0, le=100)
    start_mood: str | None = None
    end_mood: str | None = None
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
    prompt: str | None = None  # prompt libero: usato dall'AI agent in MVP 3
    use_ai: bool | None = None  # None = auto (AI se configurata e c'e' un prompt)
    # technical = mix prudente sui soli dati; creative = l'AI usa la sua conoscenza
    # musicale (vibe, arco emotivo, contrasti) restando vincolata alle candidate.
    mode: Literal["technical", "creative"] = "technical"


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
    missing_library_suggestions: list[str] = []


class SetlistTrackOut(BaseModel):
    position: int
    role: str | None = None
    track: TrackOut
    transition_score: float | None = None
    transition_reason: str | None = None
    transition_note: str | None = None
    ai_reason: str | None = None
    risk_level: str | None = None
    # F10: classificazione semantica della transizione dal brano precedente
    transition_class: str | None = None
    transition_class_label: str | None = None
    transition_class_reason: str | None = None
    # Consiglio tecnico deterministico su come mixare dal brano precedente (no AI, no id)
    mix_tip: str | None = None


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
    # Piano di mixaggio deterministico del set (come legare i brani, dove i salti).
    mixing_overview: list[str] = []
    total_duration_seconds: int = 0
    created_at: datetime
    tracks: list[SetlistTrackOut] = []


class SetlistSummaryOut(BaseModel):
    id: int
    name: str
    strategy: str | None = None
    target_duration_minutes: int | None = None
    track_count: int = 0
    total_duration_seconds: int = 0
    generated_by: str = "algorithmic"
    created_at: datetime


# --- Editing scaletta (MVP 3) -------------------------------------------------


class SetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MoveTrackRequest(BaseModel):
    direction: Literal["up", "down"]


class ReplaceTrackRequest(BaseModel):
    track_id: int


# --- Alternative per traccia (F9) --------------------------------------------


class AlternativesRequest(BaseModel):
    position: int = Field(ge=1)
    mode: Literal["safer", "softer", "harder", "same_artist", "surprising"] = "safer"
    limit: int = Field(default=5, ge=1, le=10)


class AlternativeOut(BaseModel):
    track: TrackOut
    score_prev: int | None = None  # transizione dal brano precedente
    score_next: int | None = None  # transizione verso il brano successivo
    reason: str = ""
    risk_level: str = "medium"


class AlternativesResponse(BaseModel):
    position: int
    mode: str
    alternatives: list[AlternativeOut] = []


# --- Playlist import (nuovo flusso) ------------------------------------------


class PlaylistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_playlist_id: str | None = None
    name: str
    owner: str | None = None
    url: str | None = None
    artwork_url: str | None = None
    track_count: int = 0
    kind: str = "playlist"
    imported_at: datetime


class SpotifyPlaylistRef(BaseModel):
    """Playlist disponibile su Spotify (per la selezione, prima dell'import)."""

    platform_playlist_id: str
    name: str
    owner: str | None = None
    track_count: int = 0
    url: str | None = None
    artwork_url: str | None = None


class PlaylistImportRequest(BaseModel):
    platform: Literal["spotify"] = "spotify"
    playlist_id: str  # id Spotify della playlist, oppure "liked" per i brani salvati


class PlaylistImportReport(BaseModel):
    playlist_id: int
    name: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    total: int = 0


class ManualImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)  # righe "Artista - Titolo" o CSV "artista,titolo"


# --- Analisi buchi playlist (nuovo_progetto.md sez. 6) -----------------------


class GapOut(BaseModel):
    gap_type: str
    severity: str  # info | warning
    description: str
    suggestion: str


class GapAnalysisResponse(BaseModel):
    scope: str  # playlist | library
    track_count: int
    gaps: list[GapOut] = []


# --- Discovery mode (Fase F) -------------------------------------------------


class DiscoveryCandidateOut(BaseModel):
    artist: str
    title: str
    match: float
    source: str  # similar_artist | similar_track | tag
    seed: str | None = None
    spotify_id: str | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None
    compatibility: int = 0
    explanation: str | None = None


class DiscoveryResponse(BaseModel):
    mode: str   # expand | gap
    scope: str  # nome playlist o "libreria"
    seed_count: int = 0
    candidates: list[DiscoveryCandidateOut] = []


class DiscoveryAddRequest(BaseModel):
    """Importa nella libreria dell'app una traccia scoperta dal Discovery."""

    artist: str
    title: str
    spotify_id: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None
    album_art_url: str | None = None
    url: str | None = None


class DiscoveryAddResponse(BaseModel):
    created: bool
    track: TrackOut


class DiscoveryExpandRequest(BaseModel):
    playlist_id: int
    limit: int = Field(default=20, ge=1, le=50)
    use_ai: bool | None = None  # None = auto (AI se configurata)


class LibraryStatsOut(BaseModel):
    total_tracks: int
    playlists: int = 0
    by_source: dict[str, int]
    with_bpm: int
    with_key: int
    with_features: int  # mood o energia presenti
    ready_for_set: int
    missing_metadata: int
    bpm_min: float | None = None
    bpm_max: float | None = None
    key_distribution: dict[str, int]


# --- Shazam: DJ set identificati (Fase 1) ------------------------------------


class DjSetTrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    start_offset_seconds: int | None = None
    artist: str | None = None
    title: str | None = None
    isrc: str | None = None
    confidence: int | None = None


class DjSetSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_url: str
    platform: str | None = None
    title: str | None = None
    dj_name: str | None = None
    artwork_url: str | None = None
    duration_seconds: int | None = None
    status: str
    error: str | None = None
    identified_count: int = 0
    created_at: datetime


class DjSetOut(DjSetSummaryOut):
    tracks: list[DjSetTrackOut] = []


class DjSetCreateIn(BaseModel):
    url: str = Field(min_length=4)
