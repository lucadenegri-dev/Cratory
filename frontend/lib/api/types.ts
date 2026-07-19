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
  spotify_url: string | null;
  album_art_url: string | null;
  has_local_file: boolean;
  local_path: string | null;
  local_format: string | null;
  local_bitrate: number | null;
  archived: boolean;
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
  imported_at: string;
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

export interface Gap {
  gap_type: string;
  severity: "info" | "warning";
  description: string;
  suggestion: string;
  params: Record<string, unknown>;
}

export interface GapAnalysis {
  scope: string;
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
  discogs_url: string | null;
  thumb_url: string | null;
  have: number;
  want: number;
  reasons: Reason[];
  discogs_id: number | null;
  format_badge: string | null;
}

export interface DiscoveryDigResponse {
  seed_type: string;
  value: string;
  leads: DiscoveryLead[];
  /** Quante pagine utili ha la pila del seme. <= 3 => `depth` non ha effetto. */
  pile_pages: number;
  /** Com'è stato risolto il seme. "genre" = scaffale Discogs: la UI avverte. */
  seed_resolution: "style" | "genre" | "label" | null;
  /** Conteggio grezzo della sonda: pile_pages è cappato a 100 e non distingue 43k da 4,9M. */
  pile_total: number;
}

export interface DiscoveryGenres {
  library: string[];
  styles: string[];
}

export type TrackDetail = Track;

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
}

export interface LibraryIndexJob {
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  scanned: number;
  matched: number;
  created: number;
  relinked: number;
  duplicates: number;
  lost: number;
  failed: number;
  errors: { path: string; error: string }[];
  error: string | null;
  root: string | null;
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
  organizer_url: string | null;
}

export interface ServiceStatus {
  key: string;
  name: string;
  category: string;
  configured: boolean;
  connected: boolean | null;  // null = il servizio non ha un concetto di "login"
  detail: string;
  env: string[];
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

export interface DiscogsTrack {
  position: string;
  title: string;
  duration_seconds: number | null;
}

export type DiscogsVideo = {
  youtube_video_id: string;
  title: string;
  duration_seconds: number | null;
};

export interface DiscogsRelease {
  discogs_id: number;
  title: string;
  artist: string;
  thumb_url: string | null;
  discogs_url: string | null;
  year: number | null;
  label: string | null;
  tracks: DiscogsTrack[];
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
}
