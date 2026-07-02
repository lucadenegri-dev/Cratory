"""Schemi Pydantic per request/response API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrackPlaylistRef(BaseModel):
    id: int
    name: str


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
    playlists: list[TrackPlaylistRef] = []
    added_at: datetime | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    enriched: bool = False
    enrichment_source: str | None = None
    enrichment_confidence: int | None = None
    has_local_file: bool = False
    local_path: str | None = None
    local_format: str | None = None
    local_bitrate: int | None = None


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


class TrackLookupOut(BaseModel):
    """Risposta del lookup read-only (bridge DjOrganizer): mai 404, sempre questo schema."""

    found: bool
    match: str | None = None  # "isrc" | "fuzzy" | None
    track_id: int | None = None
    artist: str | None = None
    title: str | None = None
    genre: str | None = None
    genre_secondary: str | None = None
    label: str | None = None
    year: int | None = None
    confidence: int = 0  # 100 = ISRC, 70 = fuzzy, 0 = non trovata


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
    # Disk-first: di default il set nasce SOLO da tracce possedute (file su disco),
    # cosi' e' garantito suonabile. False = includi anche i lead (senza file).
    owned_only: bool = True
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
    # Disk-first: il set e' nato "solo brani posseduti" (l'editor lo fa rispettare)
    owned_only: bool = False
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
    removed: int = 0
    skipped: int = 0
    total: int = 0


class ManualImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)  # righe "Artista - Titolo" o CSV "artista,titolo"


# --- Import locale -----------------------------------------------------------


class LocalDirEntry(BaseModel):
    name: str
    path: str
    audio_file_count: int = 0


class LocalBrowseResponse(BaseModel):
    current_path: str
    parent_path: str | None = None
    dirs: list[LocalDirEntry] = []


class LocalFolderImportRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    recurse: bool = True


class LocalImportJobStatus(BaseModel):
    status: str
    processed: int = 0
    total: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    playlist_id: int | None = None
    errors: list[dict] = []
    error: str | None = None


# --- Etichette discografiche -------------------------------------------------


class LabelStatsOut(BaseModel):
    label: str
    track_count: int
    artist_count: int
    genres: list[str] = []
    year_min: int | None = None
    year_max: int | None = None


class LabelBackfillReport(BaseModel):
    updated: int = 0
    candidates: int = 0
    remaining: int = 0
    rate_limited: bool = False


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
    source: str  # similar_artist | similar_track | tag | label
    seed: str | None = None
    spotify_id: str | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None
    label: str | None = None
    label_owned: bool = False
    explanation: str | None = None


class DiscoveryResponse(BaseModel):
    mode: str   # expand | labels
    scope: str  # nome playlist o etichette
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


class PlaylistAddTrackRequest(BaseModel):
    """Aggiunge una traccia scoperta (expand) a una playlist specifica."""

    artist: str
    title: str
    spotify_id: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None
    album_art_url: str | None = None
    url: str | None = None


class PlaylistAddTrackResponse(BaseModel):
    created: bool
    track: TrackOut
    spotify_added: bool = False
    spotify_error: str | None = None


class DiscoveryExpandRequest(BaseModel):
    playlist_id: int
    limit: int = Field(default=20, ge=1, le=50)
    use_ai: bool | None = None  # None = auto (AI se configurata)


# --- Discovery v2: dig (crate digging via Discogs) ---------------------------


class ReasonOut(BaseModel):
    """Spiegazione strutturata di un lead: codice + payload. Il testo lo rende la UI."""

    code: str
    data: dict[str, Any] = {}


class DiscoveryLeadOut(BaseModel):
    """Lead leggero NON risolto: l'identita' Spotify si ricava al salvataggio."""

    artist: str
    title: str
    year: int | None = None
    label: str | None = None
    style: str | None = None
    source: str = "discogs"
    seed: str | None = None
    discogs_url: str | None = None
    thumb_url: str | None = None
    have: int = 0
    want: int = 0
    reasons: list[ReasonOut] = []


class DiscoveryDigRequest(BaseModel):
    seed_type: Literal["genre", "label"]
    value: str = Field(min_length=1)
    adventurousness: float = Field(default=0.4, ge=0.0, le=1.0)
    limit: int = Field(default=80, ge=1, le=200)
    taste_playlist_id: int | None = None  # riferimento di gusto; None = tutta la libreria


class DiscoveryDigResponse(BaseModel):
    seed_type: str
    value: str
    leads: list[DiscoveryLeadOut] = []


class DiscoveryGenresOut(BaseModel):
    library: list[str] = []   # generi gia' presenti in libreria
    styles: list[str] = []    # stili curati (sottoinsieme Discogs) per il drill-down


class BpmBin(BaseModel):
    # 'from' e' parola chiave Python: campo from_ con alias "from" sul JSON.
    model_config = ConfigDict(populate_by_name=True)
    from_: float = Field(alias="from")
    to: float
    count: int


class EnergyBucket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: int = Field(alias="from")
    to: int
    count: int


class LibraryIndexJobStatus(BaseModel):
    """Stato del job di indicizzazione della libreria canonica (disk-first)."""

    status: str
    processed: int = 0
    total: int = 0
    scanned: int = 0
    matched: int = 0
    created: int = 0
    relinked: int = 0
    duplicates: int = 0
    unchanged: int = 0
    archived: int = 0
    lost: int = 0
    failed: int = 0
    errors: list[dict] = []
    error: str | None = None
    root: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class LibraryStatsOut(BaseModel):
    total_tracks: int
    playlists: int = 0
    by_source: dict[str, int]
    with_bpm: int
    with_key: int
    with_features: int  # mood o energia presenti
    ready_for_set: int
    with_local_file: int = 0
    missing_metadata: int
    bpm_min: float | None = None
    bpm_max: float | None = None
    key_distribution: dict[str, int]
    bpm_histogram: list[BpmBin] = []
    energy_distribution: list[EnergyBucket] = []


class PipelineOut(BaseModel):
    """Snapshot della pipeline di orientamento (dashboard). Campi disco None = non configurato."""
    playlists: int
    total_tracks: int
    missing_key: int
    wishlist: int
    with_local_file: int
    ready_for_set: int
    download_active: bool
    download_pending: int
    inbox_files: int | None = None
    files_on_disk: int | None = None
    index_mismatch: bool | None = None
    last_index_at: str | None = None
    organizer_url: str | None = None


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
