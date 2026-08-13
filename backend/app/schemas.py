"""Schemi Pydantic per request/response API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    year: int | None = None
    duration_seconds: int | None = None
    bpm: float | None = None
    camelot_key: str | None = None
    energy: int | None = None
    label: str | None = None
    status: str = "imported"
    url: str | None = None
    isrc: str | None = None
    playlists: list[TrackPlaylistRef] = []
    # Posizione 1-based nella playlist: valorizzata SOLO da GET /api/playlists/{id}/tracks.
    playlist_position: int | None = None
    # Data di aggiunta ALLA playlist (playlist_tracks.added_at): valorizzata SOLO
    # da GET /api/playlists/{id}/tracks. `added_at` resta il primo import in libreria.
    playlist_added_at: datetime | None = None
    added_at: datetime | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    has_local_file: bool = False
    local_path: str | None = None
    local_format: str | None = None
    local_bitrate: int | None = None
    archived: bool = False
    rating: int | None = None
    last_download_outcome: str | None = None
    last_download_reason: str | None = None
    last_download_path: str | None = None
    # F-tag-effettivi: i campi genre/album/label/year qui sopra portano il
    # valore EFFETTIVO (tag del primary file se non-NULL, altrimenti il valore
    # streaming). I flag dicono da dove viene ogni valore.
    primary_file_id: int | None = None
    genre_from_file: bool = False
    album_from_file: bool = False
    label_from_file: bool = False
    year_from_file: bool = False


class TrackListOut(BaseModel):
    total: int
    items: list[TrackOut]


class TrackDetailOut(TrackOut):
    """Dettaglio traccia: aggiunge artist/title letti dal file (informativi,
    l'identità resta quella della Track)."""

    file_artist: str | None = None
    file_title: str | None = None


class TrackUpdateIn(BaseModel):
    """Modifica manuale di una traccia.

    Solo i campi presenti nel payload vengono toccati (PATCH parziale): un valore
    `null` azzera il campo, un campo assente resta invariato. I valori inseriti a
    mano sovrascrivono sempre quelli gia' presenti (l'utente sa cosa scrive).

    `energy` non e' modificabile a mano: e' sempre derivata da bpm/genere
    (services/energy) e viene ricalcolata in repositories.update_track quando il
    patch cambia bpm o genere. extra="forbid" rifiuta (422) un payload che la
    contenga.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    year: int | None = Field(default=None, ge=0, le=3000)
    duration_seconds: int | None = Field(default=None, ge=0)
    bpm: float | None = Field(default=None, gt=0, le=400)
    camelot_key: str | None = None
    label: str | None = None
    # Archivia/ripristina dalla wishlist. Bool NOT NULL: null = invariato
    # (il "null azzera" degli altri campi non si applica, vedi patch_track).
    archived: bool | None = None
    # Voto 1..3; null esplicito = toglie il voto (semantica PATCH standard).
    rating: int | None = Field(default=None, ge=1, le=3)


class TrackLinkFileIn(BaseModel):
    """Collegamento manuale di un file su disco alla traccia."""

    path: str


class TransitionScoreOut(BaseModel):
    score: int = Field(ge=0, le=100)
    technical_reasons: list[str] = []
    warnings: list[str] = []
    # F10: classificazione semantica (technically_safe | creative_risk | good_reset)
    classification: str | None = None
    classification_reason: str | None = None


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
    # progressione di energia (0-100) lungo il set
    start_energy: int | None = Field(default=None, ge=0, le=100)
    end_energy: int | None = Field(default=None, ge=0, le=100)
    seed_artists: list[str] = []
    # filtro genere: match esatto sui tag di libreria; vuoto = tutti i generi
    genres: list[str] = []
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
    prompt: str | None = None  # prompt libero: interpretato dalla curatela AI
    use_ai: bool | None = None  # None = auto (AI se configurata e c'e' un prompt)


class SetlistTrackOut(BaseModel):
    position: int
    role: str | None = None
    track: TrackOut
    transition_score: float | None = None
    transition_reason: str | None = None
    transition_note: str | None = None
    ai_reason: str | None = None
    risk_level: str | None = None
    mood_tags: list[str] = []
    # F10: classificazione semantica della transizione dal brano precedente
    transition_class: str | None = None
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
    curation: dict = {}
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
    """Sposta una traccia: passo singolo (`direction`, per le frecce/tastiera) oppure
    posizione arbitraria (`to`, 1-based, per il drag-and-drop). Esattamente uno dei due.
    """

    direction: Literal["up", "down"] | None = None
    to: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> "MoveTrackRequest":
        if (self.direction is None) == (self.to is None):
            raise ValueError("Specificare esattamente uno tra 'direction' e 'to'")
        return self


class ReplaceTrackRequest(BaseModel):
    track_id: int


class AddTrackRequest(BaseModel):
    track_id: int
    position: int | None = Field(default=None, ge=1)


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


class PlaylistFromTracksRequest(BaseModel):
    """Creazione playlist componendo tracce gia' in libreria (disk-first)."""
    name: str = Field(min_length=1)
    track_ids: list[int] = Field(min_length=1)


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
    name_locked: bool = False
    imported_at: datetime


class PlaylistDuplicateRequest(BaseModel):
    """Fork della playlist in una copia manuale (riordinabile/editabile)."""
    name: str | None = Field(default=None, max_length=200)


class PlaylistUpdateIn(BaseModel):
    """Rename di una playlist. Il nome scelto blocca la sovrascrittura del sync."""
    name: str = Field(min_length=1, max_length=200)


class PlaylistAddTracksRequest(BaseModel):
    """Aggiunta di tracce di libreria a una playlist esistente."""
    track_ids: list[int] = Field(min_length=1)


class PlaylistAddTracksResult(BaseModel):
    playlist: PlaylistOut
    added: int
    skipped: int


class PlaylistReorderRequest(BaseModel):
    track_id: int
    position: int = Field(ge=1)


class PlaylistOrderRequest(BaseModel):
    """Ordine completo della playlist: permutazione esatta dei membri."""
    track_ids: list[int] = Field(min_length=1)


class PlaylistDeleteResult(BaseModel):
    """Esito eliminazione playlist: quante tracce-lead orfane sono state rimosse."""

    deleted_tracks: int = 0


class PlaylistRemoveTracksRequest(BaseModel):
    """Rimozione bulk di tracce dalla playlist."""
    track_ids: list[int] = Field(min_length=1)


class PlaylistBulkRemoveResult(BaseModel):
    removed: int = 0          # membership tolte
    deleted_tracks: int = 0   # lead orfani cancellati dalla libreria


class SyncTrackRef(BaseModel):
    """Riferimento snapshot a una traccia in un evento di sync (l'id puo' essere
    di una traccia nel frattempo cancellata come lead orfano)."""
    id: int | None = None
    artist: str | None = None
    title: str | None = None


class PlaylistSyncEventOut(BaseModel):
    """Un import/sync che ha cambiato la playlist: cosa e' entrato e uscito."""

    id: int
    created_at: datetime
    added: list[SyncTrackRef] = []
    removed: list[SyncTrackRef] = []


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


class LikedTrackPreview(BaseModel):
    spotify_id: str
    isrc: str | None = None
    title: str | None = None
    artist: str | None = None
    duration_seconds: int | None = None
    artwork_url: str | None = None
    already_imported: bool = False


class LikedSelectedImportRequest(BaseModel):
    spotify_ids: list[str] = Field(default_factory=list)


class PlaylistImportReport(BaseModel):
    playlist_id: int
    name: str
    created: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    total: int = 0


class PlaylistSyncFailure(BaseModel):
    """Una playlist che il sync di massa non è riuscito a riallineare."""

    playlist_id: int
    name: str
    platform: str
    error: str


class PlaylistsSyncAllReport(BaseModel):
    """Esito aggregato del sync di massa: i conteggi sono la somma sulle playlist
    riuscite, `failures` elenca quelle saltate con il motivo."""

    synced: int
    failed: int
    created: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    failures: list[PlaylistSyncFailure] = []


class StreamingImportJobStatus(BaseModel):
    """Stato del job unico di import/sync streaming (Spotify/SoundCloud): import
    playlist/liked, import selettivo dei liked, sync. Un solo job alla volta."""

    status: str
    kind: str | None = None
    phase: str | None = None  # fetching | importing
    processed: int = 0
    total: int = 0
    result: PlaylistImportReport | None = None
    # Sync di massa: la playlist in corso col suo progresso interno ("Techno · 45/120").
    current_label: str | None = None
    # Valorizzato solo dal kind playlists_sync_all (per gli altri kind vale `result`).
    sync_all: PlaylistsSyncAllReport | None = None
    error: str | None = None
    error_code: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ManualImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)  # righe "Artista - Titolo" o CSV "artista,titolo"


# --- SoundCloud ---------------------------------------------------------------


class SoundCloudStatus(BaseModel):
    available: bool  # yt-dlp importabile
    ytdlp_version: str | None = None
    username: str | None = None


class SoundCloudConfigRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)


class SoundCloudImportRequest(BaseModel):
    url: str = Field(min_length=1)  # playlist pubblica o secret link


class SoundCloudLikedTrackPreview(BaseModel):
    track_id: str
    title: str | None = None  # grezzo, come appare su SoundCloud (split all'import)
    uploader: str | None = None  # utente che ha caricato, dallo slug dell'URL
    duration_seconds: int | None = None
    artwork_url: str | None = None
    url: str | None = None
    already_imported: bool = False


class SoundCloudLikedSelectedRequest(BaseModel):
    track_ids: list[str] = Field(default_factory=list)
    # Quanti like rifetchare per filtrare i selezionati. None = tutti: deve
    # coprire almeno la stessa finestra della preview, altrimenti una traccia
    # selezionata oltre il limite non verrebbe ritrovata all'import.
    limit: int | None = None


# --- Import locale -----------------------------------------------------------


class LocalDirEntry(BaseModel):
    name: str
    path: str
    audio_file_count: int = 0
# --- Etichette discografiche -------------------------------------------------


class LabelStatsOut(BaseModel):
    label: str
    track_count: int
    artist_count: int
    artists: list[str] = []
    genres: list[str] = []
    year_min: int | None = None
    year_max: int | None = None


# --- Analisi buchi playlist (nuovo_progetto.md sez. 6) -----------------------


class GapOut(BaseModel):
    gap_type: str
    severity: str  # info | warning
    description: str
    suggestion: str
    # Numeri/stringhe delle f-string di description/suggestion, per la traduzione
    # frontend (namespace i18n `gaps`, vedi lib/i18n/runtime.ts::translateGap).
    params: dict[str, Any] = {}


class GapAnalysisResponse(BaseModel):
    scope: str  # playlist | library
    track_count: int
    gaps: list[GapOut] = []


# --- Discovery: import/salvataggio lead del dig -----------------------------


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
    # Neutro: due sorgenti non stanno in un campo che si chiama `discogs_id`. Stringa
    # perche' Bandcamp ci mette una coppia "band_id:item_id".
    source_id: str | None = None
    source_url: str | None = None
    # Stream diretto quando la sorgente lo regala (Bandcamp): il player salta la
    # risoluzione iTunes/YouTube e suona.
    stream_url: str | None = None
    thumb_url: str | None = None
    have: int = 0
    want: int = 0
    reasons: list[ReasonOut] = []
    format_badge: str | None = None


class DiscoveryDigRequest(BaseModel):
    seed_type: Literal["genre", "label"]
    value: str = Field(min_length=1)
    # DOVE pescare nella pila della sorgente: 0 = la cima, 1 = il fondo di cio' che
    # la sorgente raggiunge. Non e' un mix di ordinamento: sceglie il bacino.
    depth: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["discogs", "bandcamp"] = "discogs"


class DiscoveryDigResponse(BaseModel):
    seed_type: str
    value: str
    source: str = "discogs"
    leads: list[DiscoveryLeadOut] = []
    # Quanto e' alta la pila (0 = seme che la sorgente non conosce).
    pile_total: int = 0
    # Quanti item la sorgente raggiunge. <= 300 => la finestra e' l'intera pila e
    # `depth` non ha effetto. < pile_total => la UI avverte che si vede una porzione.
    pile_reach: int = 0
    # "style"|"genre"|"label"|"tag"|"discography"|null
    seed_resolution: str | None = None


class DiscoveryGenresOut(BaseModel):
    library: list[str] = []   # generi gia' presenti in libreria
    styles: list[str] = []    # stili curati (sottoinsieme Discogs) per il drill-down


class DiscoveryTrackOut(BaseModel):
    position: str
    title: str
    duration_seconds: int | None = None
    # Popolato solo da Bandcamp: le tracce Discogs non hanno audio.
    stream_url: str | None = None


class DiscogsVideoOut(BaseModel):
    youtube_video_id: str
    title: str
    duration_seconds: int | None = None


class DiscoveryReleaseOut(BaseModel):
    source: str
    source_id: str
    source_url: str | None = None
    title: str
    artist: str
    thumb_url: str | None = None
    year: int | None = None
    label: str | None = None
    tracks: list[DiscoveryTrackOut] = []
    # Video YouTube della release: solo Discogs. Su Bandcamp e' sempre vuota, perche'
    # le tracce hanno gia' lo stream vero.
    videos: list[DiscogsVideoOut] = []


class DiscoverySaveForLaterRequest(BaseModel):
    """Una traccia della tracklist di un disco, segnata 'per dopo'."""

    artist: str
    title: str
    duration_seconds: int | None = None
    album_art_url: str | None = None
    url: str | None = None


class DiscoverySaveForLaterResponse(BaseModel):
    created: bool
    track: TrackOut


class DiscoveryPreviewOut(BaseModel):
    kind: str  # "itunes" | "youtube" | "none"
    audio_url: str | None = None
    youtube_video_id: str | None = None
    source_url: str | None = None
    matched_title: str | None = None


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


class AnalysisJobStatus(BaseModel):
    """Stato del job di analisi BPM/key in-app (pagina Analisi)."""

    status: str
    processed: int = 0
    total: int = 0
    analyzed: int = 0
    failed: int = 0
    applied: int = 0
    current_label: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class AnalysisStartIn(BaseModel):
    """Avvio del job: scope 'missing' (default) | 'all', o track_ids espliciti."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["missing", "all"] = "missing"
    track_ids: list[int] | None = None


class AnalysisOverviewOut(BaseModel):
    """Copertura BPM/key della libreria posseduta, per la pagina Analisi."""

    owned: int
    ready_for_set: int
    missing_bpm: int
    missing_key: int
    bpm_by_source: dict[str, int]
    key_by_source: dict[str, int]
    analyzed: int
    divergent: int
    rekordbox_pending: int


class AnalysisDivergenceOut(BaseModel):
    """Riga della tabella divergenze: canonico vs analisi in-app."""

    track_id: int
    artist: str | None = None
    title: str | None = None
    bpm: float | None = None
    bpm_source: str | None = None
    analysis_bpm: float | None = None
    bpm_delta: float | None = None
    camelot_key: str | None = None
    key_source: str | None = None
    analysis_camelot: str | None = None
    key_compatibility: str  # same | compatible | weak | unknown


class AnalysisApplyIn(BaseModel):
    """Apply dei valori analizzati: per id, per modo, o riscrittura totale (force)."""

    model_config = ConfigDict(extra="forbid")

    track_ids: list[int] | None = None
    mode: Literal["divergent", "all"] | None = None
    force: bool = False


class AnalysisApplyOut(BaseModel):
    applied: int
    skipped: int


class LibraryStatsOut(BaseModel):
    total_tracks: int
    playlists: int = 0
    by_source: dict[str, int]
    with_bpm: int
    with_key: int
    with_features: int  # energia presente
    ready_for_set: int
    with_local_file: int = 0
    missing_metadata: int
    bpm_min: float | None = None
    bpm_max: float | None = None
    key_distribution: dict[str, int]
    genre_distribution: dict[str, int] = {}
    bpm_histogram: list[BpmBin] = []
    energy_distribution: list[EnergyBucket] = []


class GenreCountOut(BaseModel):
    genre: str
    count: int


class GenerateAsyncStartOut(BaseModel):
    """Risposta immediata di POST /api/sets/generate-async: il job e' partito
    in background, seguire /generate-status per l'esito."""

    status: str
    phase: str | None = None
    using_ai: bool


class GenerateStatusOut(BaseModel):
    """Stato del job di generazione asincrona (GET /api/sets/generate-status)."""

    status: str
    phase: str | None = None
    using_ai: bool = False
    setlist_id: int | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class PipelineOut(BaseModel):
    """Snapshot della pipeline di orientamento (dashboard). Campi disco None = non configurato."""
    playlists: int
    total_tracks: int
    missing_key: int
    wishlist: int
    archived_count: int = 0
    with_local_file: int
    analyze_pending: int
    ready_for_set: int
    download_active: bool
    download_pending: int
    inbox_files: int | None = None


# --- Shazam: DJ set identificati (Fase 1) ------------------------------------


class DjSetTrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    start_offset_seconds: int | None = None
    artist: str | None = None
    title: str | None = None
    isrc: str | None = None
    confidence: int | None = None
    # Cross-match deterministico con la libreria (ISRC poi artista+titolo esatto):
    # None/None se nessuna Track corrisponde. "owned" = file su disco, "in_library"
    # = presente in libreria/lead ma senza file locale.
    library_track_id: int | None = None
    library_status: Literal["owned", "in_library"] | None = None


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
    aborted_at_seconds: int | None = None  # analisi parziale: dove si e' fermata
    imported_playlist_id: int | None = None
    created_at: datetime


class DjSetOut(DjSetSummaryOut):
    tracks: list[DjSetTrackOut] = []


class MixIdentifyStatusOut(BaseModel):
    """Stato del job di identificazione mix (GET /api/shazam/identify-status)."""

    status: str
    phase: str | None = None
    processed: int = 0
    total: int = 0
    dj_set_id: int | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class MixIdentifyStartOut(MixIdentifyStatusOut):
    """Risposta di POST /api/shazam/identify: come lo stato, piu' `cached`
    (True se l'URL era gia' stato identificato con successo in precedenza)."""

    cached: bool = False


class DjSetCreateIn(BaseModel):
    url: str = Field(min_length=4)
