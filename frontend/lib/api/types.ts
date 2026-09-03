import type { SecretKey, SecretState } from "./setup";

export interface Track {
  id: number;
  spotify_id: string | null;
  soundcloud_id: string | null;
  source_type: string;
  platform: string | null;
  title: string | null;
  artist: string | null;
  album: string | null;
  genre: string | null;
  year: number | null;
  duration_seconds: number | null;
  bpm: number | null;
  camelot_key: string | null;
  energy: number | null;
  label: string | null;
  status: string;
  url: string | null;
  isrc: string | null;
  playlists: { id: number; name: string }[];
  added_at: string | null;
  /** Data di aggiunta ALLA playlist: presente solo da GET /playlists/{id}/tracks. */
  playlist_added_at: string | null;
  spotify_url: string | null;
  album_art_url: string | null;
  has_local_file: boolean;
  local_path: string | null;
  local_format: string | null;
  local_bitrate: number | null;
  primary_file_id: number | null;
  genre_from_file: boolean;
  album_from_file: boolean;
  label_from_file: boolean;
  year_from_file: boolean;
  archived: boolean;
  rating: number | null;
  last_download_outcome: string | null;
  last_download_reason: string | null;
  last_download_path: string | null;
}

export interface Playlist {
  id: number;
  platform: string;
  platform_playlist_id: string | null;
  name: string;
  owner: string | null;
  url: string | null;
  artwork_url: string | null;
  track_count: number;
  kind: string;
  name_locked: boolean;
  imported_at: string;
}

export interface SyncTrackRef {
  id: number | null;
  artist: string | null;
  title: string | null;
}

/** Un import/sync che ha cambiato la playlist: cosa è entrato e uscito. */
export interface PlaylistSyncEvent {
  id: number;
  created_at: string;
  added: SyncTrackRef[];
  removed: SyncTrackRef[];
}

export interface PlaylistAddTracksResult {
  playlist: Playlist;
  added: number;
  skipped: number;
}

export interface SpotifyPlaylistRef {
  platform_playlist_id: string;
  name: string;
  owner: string | null;
  track_count: number;
  url: string | null;
  artwork_url: string | null;
}

export interface PlaylistImportReport {
  playlist_id: number;
  name: string;
  created: number;
  updated: number;
  removed: number;
  skipped: number;
  total: number;
}

export interface PlaylistSyncFailure {
  playlist_id: number;
  name: string;
  platform: string;
  error: string;
}

/** Esito aggregato del sync di massa (kind `playlists_sync_all`). */
export interface PlaylistsSyncAllReport {
  synced: number;
  failed: number;
  created: number;
  updated: number;
  removed: number;
  skipped: number;
  failures: PlaylistSyncFailure[];
}

export interface Gap {
  gap_type: string;
  severity: "info" | "warning";
  description: string;
  suggestion: string;
  params: Record<string, unknown>;
}

export interface GapAnalysis {
  track_count: number;
  gaps: Gap[];
}

export interface SpotifyStatus {
  configured: boolean;
  user_connected: boolean;
  redirect_uri: string;
}

export interface DiscoveryAddResponse {
  created: boolean;
  track: Track;
}

// Discovery v2: dig (crate digging via Discogs) — lead leggeri non risolti.
export interface Reason {
  code: string;
  data: Record<string, string | number>;
}

export interface DiscoveryLead {
  artist: string;
  title: string;
  year: number | null;
  label: string | null;
  style: string | null;
  source: string;
  seed: string | null;
  /** Id neutro. Discogs: "123". Bandcamp: "band_id:item_id" (il dettaglio vuole entrambi). */
  source_id: string | null;
  source_url: string | null;
  /** Stream diretto quando la sorgente lo regala: il player salta la risoluzione. */
  stream_url: string | null;
  thumb_url: string | null;
  have: number;
  want: number;
  reasons: Reason[];
  format_badge: string | null;
}

export interface DiscoveryDigResponse {
  seed_type: string;
  value: string;
  source: string;
  leads: DiscoveryLead[];
  /** Quanto è alta la pila. 0 => seme che la sorgente non conosce. */
  pile_total: number;
  /** Quanti item la sorgente raggiunge. <= WINDOW_ITEMS => `depth` non ha effetto. */
  pile_reach: number;
  seed_resolution: "style" | "genre" | "label" | "tag" | "discography" | null;
}

export interface DiscoveryGenres {
  library: string[];
  styles: string[];
}

export interface TrackDetail extends Track {
  file_artist: string | null;
  file_title: string | null;
}

/** Campi modificabili a mano da libreria / gestione playlist. */
export interface TrackUpdate {
  title?: string | null;
  artist?: string | null;
  album?: string | null;
  genre?: string | null;
  year?: number | null;
  duration_seconds?: number | null;
  bpm?: number | null;
  camelot_key?: string | null;
  label?: string | null;
  archived?: boolean;
  rating?: number | null;
}

/** Report combinato delle quattro parti dell'aggancio (collega_tracce +
 *  indicizza_archivio + riconcilia_possessi + recompute_energy), copia di
 *  `link_report` in `app/services/library_index.py`. */
/** Rispecchia `LinkingReport` (backend/app/organize/schemas.py). I contatori
 *  del giro d'archivio sono distinti da quelli di libreria: `unchanged` di
 *  libreria (riga già agganciata e invariata) e `archive_unchanged` (file
 *  scartato già visto) non sono la stessa cosa, e finché erano sommati sotto
 *  una chiave sola il numero non significava nulla. */
export interface LibraryIndexLinking {
  scanned: number;
  matched: number;
  created: number;
  relinked: number;
  lost: number;
  orphans_removed: number;
  created_ids: number[];
  /** null se la fase non è girata (radice smontata). */
  energy_computed: number | null;
  duplicates: number;
  failed: number;
  unchanged: number;
  archive_duplicates: number;
  archive_failed: number;
  archive_unchanged: number;
  /** Tracce marcate come scartate: lo produce solo il giro d'archivio. */
  archived: number;
  errors: { path: string; error: string }[];
}

/** Esito di uno scan+link completo: forma di `ScanSummary` (app/organize/schemas.py),
 *  più `analysis` valorizzato dal job (app/organize/services/scan_job.py). */
export interface LibraryIndexResult {
  roots: number[];
  found: number;
  inserted: number;
  updated: number;
  unchanged: number;
  moved: number;
  missing: number;
  errors: number;
  started_at: string | null;
  finished_at: string | null;
  linking: LibraryIndexLinking | null;
  analysis?: {
    issues_total: number;
    issues_by_severity: Record<string, number>;
    dup_groups: number;
    dup_files: number;
  };
}

/** Stato del job unico di scan+link (`scan_job.job_state()`): stessa forma sia
 *  che sia stato avviato da `/api/library/index` (Cratory) sia da
 *  `/api/organize/scan` (Organize) — è lo stesso job in entrambi i casi. */
export interface LibraryIndexJob {
  status: "idle" | "running" | "done" | "error";
  /** scanning/linking dallo scanner; inspecting/deduping da analysis.recompute. */
  phase: "scanning" | "linking" | "inspecting" | "deduping" | null;
  processed: number;
  total: number;
  result: LibraryIndexResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface AnalysisJobStatus {
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  analyzed: number;
  failed: number;
  applied: number;
  current_label: string | null;
  error: string | null;
}

export interface AnalysisOverview {
  owned: number;
  ready_for_set: number;
  missing_bpm: number;
  missing_key: number;
  bpm_by_source: Record<string, number>;
  key_by_source: Record<string, number>;
  analyzed: number;
  divergent: number;
  rekordbox_pending: number;
}

export interface AnalysisDivergence {
  track_id: number;
  artist: string | null;
  title: string | null;
  bpm: number | null;
  bpm_source: string | null;
  analysis_bpm: number | null;
  bpm_delta: number | null;
  camelot_key: string | null;
  key_source: string | null;
  analysis_camelot: string | null;
  key_compatibility: "same" | "compatible" | "weak" | "unknown";
}

/** Snapshot della pipeline di orientamento (dashboard). Campi disco null = non configurato. */
export interface PipelineStatus {
  playlists: number;
  total_tracks: number;
  missing_key: number;
  wishlist: number;
  archived_count: number;
  with_local_file: number;
  analyze_pending: number;
  ready_for_set: number;
  download_active: boolean;
  download_pending: number;
  inbox_files: number | null;
}

export interface ServiceStatus {
  key: string;
  name: string;
  category: string;
  configured: boolean;
  connected: boolean | null;  // null = il servizio non ha un concetto di "login"
  detail: string;
  env: string[];
  /** Variabili facoltative (es. DISCOGS_TOKEN): la loro assenza non rende il
   *  servizio "non configurato", solo "token consigliato". */
  optional_env: string[];
  /** true/false = facoltative presenti/assenti; null = il servizio non ne ha. */
  optional_ok: boolean | null;
  docs: string;
}

export type TransitionClass = "technically_safe" | "creative_risk" | "good_reset";

export interface TransitionScore {
  score: number;
  technical_reasons: string[];
  warnings: string[];
  classification: TransitionClass | null;
  classification_reason: string | null;
}

export interface TransitionCandidate {
  track: Track;
  score: TransitionScore;
}

export interface SetlistTrack {
  position: number;
  role: string | null;
  track: Track;
  transition_score: number | null;
  transition_reason: string | null;
  transition_note: string | null;
  ai_reason: string | null;
  risk_level: string | null;
  transition_class: TransitionClass | null;
  transition_class_reason: string | null;
  mix_tip: string | null;
  mood_tags: string[];
}

export interface SetlistValidation {
  warnings?: string[];
  auto_fixes?: string[];
  critical_points?: string[];
  alternative_directions?: string[];
  missing_library_suggestions?: string[];
  stats?: Record<string, number>;
}

export interface Setlist {
  id: number;
  name: string;
  strategy: string | null;
  target_duration_minutes: number | null;
  global_explanation: string | null;
  generated_by: string;
  owned_only: boolean;
  validation: SetlistValidation;
  mixing_overview: string[];
  total_duration_seconds: number;
  created_at: string;
  tracks: SetlistTrack[];
  curation: {
    intent_summary?: string;
    compiled?: Record<string, unknown>;
    warnings?: string[];
  };
}

export interface SetlistSummary {
  id: number;
  name: string;
  strategy: string | null;
  target_duration_minutes: number | null;
  track_count: number;
  total_duration_seconds: number;
  generated_by: string;
  created_at: string;
}

export type AlternativeMode = "safer" | "softer" | "harder" | "same_artist" | "surprising";

export interface Alternative {
  track: Track;
  score_prev: number | null;
  score_next: number | null;
  reason: string;
  risk_level: string;
}

export interface AlternativesResponse {
  position: number;
  mode: AlternativeMode;
  alternatives: Alternative[];
}

export interface AiStatus {
  configured: boolean;
  model: string | null;
}

export interface GenStatus {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  using_ai: boolean;
  setlist_id: number | null;
  error: string | null;
}

export interface BpmBin {
  from: number;
  to: number;
  count: number;
}

export interface EnergyBucket {
  from: number;
  to: number;
  count: number;
}

export interface LibraryStats {
  total_tracks: number;
  playlists: number;
  by_source: Record<string, number>;
  with_bpm: number;
  with_key: number;
  with_features: number;
  with_local_file: number;
  ready_for_set: number;
  missing_metadata: number;
  bpm_min: number | null;
  bpm_max: number | null;
  key_distribution: Record<string, number>;
  genre_distribution: Record<string, number>;
  bpm_histogram: BpmBin[];
  energy_distribution: EnergyBucket[];
}

/** Stato del job unico di import/sync streaming (Spotify/SoundCloud): il fetch
 *  dalla piattaforma, potenzialmente lento su librerie di migliaia di brani,
 *  gira in background. Un solo job alla volta (poller in JobsProvider). */
export interface StreamingImportJobStatus {
  status: "idle" | "running" | "done" | "error";
  kind: string | null;
  phase: "fetching" | "importing" | null;
  processed: number;
  total: number;
  result: PlaylistImportReport | null;
  /** Sync di massa: playlist in corso col suo progresso interno. */
  current_label: string | null;
  /** Valorizzato solo dal sync di massa; per gli altri kind vale `result`. */
  sync_all: PlaylistsSyncAllReport | null;
  error: string | null;
  error_code: string | null;
}

export interface LikedTrackPreview {
  spotify_id: string;
  isrc: string | null;
  title: string | null;
  artist: string | null;
  duration_seconds: number | null;
  artwork_url: string | null;
  already_imported: boolean;
}

export interface SoundCloudStatus {
  available: boolean;
  ytdlp_version: string | null;
  username: string | null;
}

/** Stato del login alla rete Soulseek via il demone slskd. `configured` = SLSKD_URL
 *  presente; `reachable` = il demone ha risposto. I flag di connessione contano
 *  solo se `reachable`. */
export interface SlskdStatus {
  configured: boolean;
  reachable: boolean;
  is_connected: boolean;
  is_logged_in: boolean;
  is_connecting: boolean;
  is_transitioning: boolean;
  state: string | null;
  username: string | null;
  /** Il demone ha risposto ma ha rifiutato la chiave API di Cratory (401/403).
   *  Diverso da `reachable: false`: e' acceso, e la strada per uscirne non e'
   *  "avvialo" ma "riscrivi la chiave e riavvialo". */
  unauthorized: boolean;
  /** URL della web UI di slskd (= SLSKD_URL), valorizzato appena configurato
   *  anche se il demone e' irraggiungibile; null se non configurato. */
  web_url: string | null;
}

/** Stato di un singolo campo di config editabile (path/URL). `source` dice se il
 *  valore effettivo viene da un override DB o dal default `.env`. */
export interface FieldState {
  value: string;
  source: "env" | "db";
  valid: boolean;
  detail: string | null;
}

/** Config editabile dalla pagina Settings + flag condivisione libreria. */
export interface ConfigSettings {
  library_root: FieldState;
  archive_root: FieldState;
  slskd_download_dir: FieldState;
  slskd_url: FieldState;
  slskd_config_path: FieldState;
  share_library: boolean;
  download_slots: number;
  /** Avviso soft (es. share non ri-applicata dopo un cambio di libreria). */
  warning: string | null;
  ai_model: FieldState;
  secrets: Record<SecretKey, SecretState>;
  spotify_redirect_uri: string;
}

/** Corpo del PATCH: campo assente = invariato; stringa vuota = azzera l'override. */
export interface ConfigPatch {
  library_root?: string;
  archive_root?: string;
  slskd_download_dir?: string;
  slskd_url?: string;
  slskd_config_path?: string;
  ai_model?: string;
  spotify_client_id?: string;
  spotify_client_secret?: string;
  ai_api_key?: string;
  discogs_token?: string;
  acoustid_api_key?: string;
  slskd_api_key?: string;
}

export interface ShareLibraryResult {
  share_library: boolean;
  /** true = slskd.yml scritto. */
  applied_to_yaml: boolean;
  /** true = rescan sul demone eseguito (false se slskd era giù: share attiva al riavvio). */
  rescan: boolean;
}

export interface SoundCloudLikedTrackPreview {
  track_id: string;
  /** Titolo grezzo, come appare su SoundCloud (lo split artista/titolo avviene all'import). */
  title: string | null;
  /** Utente che ha caricato la traccia (dallo slug dell'URL). */
  uploader: string | null;
  duration_seconds: number | null;
  artwork_url: string | null;
  url: string | null;
  already_imported: boolean;
}

export interface PlaylistDeleteResult {
  deleted_tracks: number;
}

export interface LabelStats {
  label: string;
  track_count: number;
  artist_count: number;
  artists: string[];
  genres: string[];
  year_min: number | null;
  year_max: number | null;
}

export interface DiscoveryTrack {
  position: string;
  title: string;
  duration_seconds: number | null;
  /** Popolato solo da Bandcamp: le tracce Discogs non hanno audio. */
  stream_url: string | null;
}

export type DiscogsVideo = {
  youtube_video_id: string;
  title: string;
  duration_seconds: number | null;
};

export interface DiscoveryRelease {
  source: string;
  source_id: string;
  source_url: string | null;
  title: string;
  artist: string;
  thumb_url: string | null;
  year: number | null;
  label: string | null;
  tracks: DiscoveryTrack[];
  /** Video YouTube della release: solo Discogs. Su Bandcamp e' sempre vuota. */
  videos: DiscogsVideo[];
}

export type DiscoveryPreview = {
  kind: "itunes" | "youtube" | "none";
  audio_url: string | null;
  youtube_video_id: string | null;
  source_url: string | null;
  matched_title: string | null;
};

export interface DiscoveryImportInput {
  artist: string;
  title: string;
  duration_seconds?: number | null;
  album_art_url?: string | null;
  url?: string | null;
}

export interface DjSetTrack {
  position: number;
  start_offset_seconds: number | null;
  artist: string | null;
  title: string | null;
  isrc: string | null;
  confidence: number | null;
  library_track_id: number | null;
  library_status: "owned" | "in_library" | null;
}

export interface DjSet {
  id: number;
  source_url: string;
  platform: string | null;
  title: string | null;
  dj_name: string | null;
  artwork_url: string | null;
  duration_seconds: number | null;
  status: "pending" | "identifying" | "done" | "error";
  error: string | null;
  identified_count: number;
  /** Analisi parziale: offset (s) a cui si è interrotta; null = completa. */
  aborted_at_seconds: number | null;
  imported_playlist_id: number | null;
  created_at: string;
}

export interface DjSetDetail extends DjSet {
  tracks: DjSetTrack[];
}

export interface ShazamIdentifyState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  dj_set_id: number | null;
  error: string | null;
  cached?: boolean;
}

export type DownloadCandidate = {
  username: string;
  filename: string;
  size: number | null;
  bitrate: number | null;
  length: number | null;
  format: string | null;
  name_score: number;
  quality_tier: number;
  confidence: number;
};

/** Un file dai risultati della ricerca Soulseek manuale (POST /api/downloads/search). */
export type SoulseekSearchFile = {
  username: string;
  filename: string;
  size: number | null;
  bitrate: number | null;
  length: number | null;
  format: string | null;
  has_free_slot: boolean;
  queue_length: number | null;
  upload_speed: number | null;
  // Presenti solo se la ricerca aveva un track_id: guida, mai esclusione.
  score: number | null;
  confidence: number | null;
  auto_ok: boolean;
};

export type SoulseekSearchResult = { variants: string[]; results: SoulseekSearchFile[] };

/** Esito di un singolo download Soulseek (stessi valori di Track.last_download_outcome). */
export type DownloadOutcome = "downloaded" | "needs_review" | "not_found" | "failed";

export type DownloadItem = {
  // null per i download da ricerca manuale (nessuna traccia collegata).
  track_id: number | null;
  artist: string | null;
  title: string | null;
  outcome: DownloadOutcome;
  // Motivo dell'esito (es. durata incoerente per needs_review).
  reason: string | null;
};

export type DownloadStatus = {
  available: boolean;
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  downloaded: number;
  needs_review: number;
  not_found: number;
  failed: number;
  playlist_id: number | null;
  items: DownloadItem[];
  error: string | null;
  // Traccia in lavorazione ("Artista — Titolo"), null a riposo.
  current_label: string | null;
};

export interface LocalFileHit {
  path: string;
  name: string;
  format: string | null;
  size: number | null;
  source: "library" | "downloads";
}

export type DownloadReview = {
  expected: { artist: string | null; title: string | null; duration_seconds: number | null };
  downloaded: {
    path: string; name: string; format: string | null; bitrate: number | null;
    duration_seconds: number | null; size: number | null;
  } | null;
  reason: string | null;
};

export type AutoLinkProposal = {
  track_id: number;
  label: string;
  artist: string | null;
  title: string | null;
  hit: { path: string; name: string; format: string | null; size: number | null; source: "library" | "downloads" } | null;
};

export interface RekordboxImportReport {
  in_file: number;
  matched: number;
  unmatched: number;
  bpm_set: number;
  key_set: number;
  energy_set: number;
  /** Tracce con valore gia' corretto ma provenienza allineata a Rekordbox. */
  source_realigned: number;
}

// --- Coda di acquisizione (/api/downloads/queue) ---------------------------

export type QueueItemState = "queued" | "running" | "done" | "cancelled";
export type QueueItemOutcome = "downloaded" | "needs_review" | "not_found" | "failed";

export type QueueItem = {
  id: number;
  track_id: number;
  label: string;
  kind: "soulseek_auto" | "soulseek_chosen" | "soundcloud";
  state: QueueItemState;
  outcome: QueueItemOutcome | null;
  phase: "searching" | "downloading" | null;
  bytes_done: number | null;
  bytes_total: number | null;
  attempts: number;
  error: string | null;
  position: number;
};

/** Esito di un accodamento.
 *
 *  `replaced` è il terzo caso: una richiesta con candidato esplicito su una
 *  traccia già in attesa ne sostituisce il carico invece di essere scartata.
 *  Va distinto dagli altri due, altrimenti l'utente sceglie a mano un file e
 *  nulla, a schermo, gli conferma che verrà usato quello. */
export type EnqueueOutcome = { enqueued: number; skipped: number; replaced: number };

/** Interruttore su slskd: `reason` è un codice, la frase la mette il frontend. */
export type QueuePause = {
  paused: boolean;
  reason: string | null;
  retry_in_seconds: number | null;
};

export type QueueSnapshot = {
  slots: number;
  active: number;
  pause: QueuePause;
  items: QueueItem[];
};
