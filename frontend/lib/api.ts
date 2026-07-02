const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  genre_secondary: string | null;
  year: number | null;
  duration_seconds: number | null;
  bpm: number | null;
  camelot_key: string | null;
  mood: string | null;
  energy: number | null;
  danceability: number | null;
  vocalness: number | null;
  label: string | null;
  status: string;
  url: string | null;
  isrc: string | null;
  playlists: { id: number; name: string }[];
  added_at: string | null;
  spotify_url: string | null;
  album_art_url: string | null;
  enriched: boolean;
  enrichment_source: string | null;
  enrichment_confidence: number | null;
  has_local_file: boolean;
  local_path: string | null;
  local_format: string | null;
  local_bitrate: number | null;
  archived: boolean;
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

export interface DiscoveryStatus {
  configured: boolean;
  spotify_resolver: boolean;
  ai_explanations: boolean;
}

export interface DiscoveryCandidate {
  artist: string;
  title: string;
  match: number;
  source: "similar_artist" | "similar_track" | "tag" | "label";
  seed: string | null;
  spotify_id: string | null;
  spotify_url: string | null;
  album_art_url: string | null;
  isrc: string | null;
  duration_seconds: number | null;
  label?: string | null;
  label_owned?: boolean;
  explanation: string | null;
}

export interface DiscoveryResponse {
  mode: "expand" | "labels";
  scope: string;
  seed_count: number;
  candidates: DiscoveryCandidate[];
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
}

export interface DiscoveryDigResponse {
  seed_type: string;
  value: string;
  leads: DiscoveryLead[];
}

export interface DiscoveryGenres {
  library: string[];
  styles: string[];
}

export interface FeatureProviderStatus {
  configured: boolean;
  provider: string | null;
}

export interface FeatureEnrichReport {
  enriched: number;
  provider_matches: number;
  metadata_enriched: number;
  not_found: number;
  total: number;
  cache_hits: number;
  with_bpm: number;
  with_key: number;
  ready_for_set: number;
  missing_core_features: number;
  field_counts: Record<string, number>;
  lookup_sources: Record<string, number>;
}

export interface FeatureEnrichJob {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: FeatureEnrichReport | null;
  error: string | null;
}

export const SPOTIFY_LOGIN_URL = `${API}/api/spotify/login`;

export type TrackDetail = Track;

/** Campi modificabili a mano da libreria / gestione playlist. */
export interface TrackUpdate {
  title?: string | null;
  artist?: string | null;
  album?: string | null;
  genre?: string | null;
  genre_secondary?: string | null;
  year?: number | null;
  duration_seconds?: number | null;
  bpm?: number | null;
  camelot_key?: string | null;
  mood?: string | null;
  energy?: number | null;
  danceability?: number | null;
  vocalness?: number | null;
  label?: string | null;
}

/** Modifica manuale di una traccia: i valori inseriti hanno la precedenza sull'enrichment. */
export function updateTrack(id: number, patch: TrackUpdate) {
  return apiPatch<TrackDetail>(`/api/tracks/${id}`, patch);
}

/** Arricchisce le feature musicali di UNA traccia (sincrono). Ritorna la traccia aggiornata. */
export function enrichTrack(id: number) {
  return apiPost<TrackDetail>(`/api/tracks/${id}/enrich`);
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

/** Indicizza la libreria canonica (LIBRARY_ROOT): il disco è la libreria. */
export function startLibraryIndex() {
  return apiPost<LibraryIndexJob>("/api/library/index");
}

export function libraryIndexStatus() {
  return apiGet<LibraryIndexJob>("/api/library/index/status");
}

/** Snapshot della pipeline di orientamento (dashboard). Campi disco null = non configurato. */
export interface PipelineStatus {
  playlists: number;
  total_tracks: number;
  missing_key: number;
  wishlist: number;
  archived_count: number;
  with_local_file: number;
  ready_for_set: number;
  download_active: boolean;
  download_pending: number;
  inbox_files: number | null;
  files_on_disk: number | null;
  index_mismatch: boolean | null;
  last_index_at: string | null;
  organizer_url: string | null;
}

export function getPipeline() {
  return apiGet<PipelineStatus>("/api/pipeline");
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
  classification_label: string | null;
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
  transition_class_label: string | null;
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
  bpm_histogram: BpmBin[];
  energy_distribution: EnergyBucket[];
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(API + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return handle<T>(await fetch(url));
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiSend<T>("POST", path, body);
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return apiSend<T>("PATCH", path, body);
}

export async function apiDelete<T>(path: string): Promise<T> {
  return apiSend<T>("DELETE", path);
}

async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(API + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export async function exportSet(setId: number, format: "text" | "csv" | "markdown"): Promise<string> {
  const res = await fetch(`${API}/api/sets/${setId}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

// --- Playlist (nuovo flusso) ------------------------------------------------

export function listSpotifyPlaylists() {
  return apiGet<SpotifyPlaylistRef[]>("/api/playlists/spotify/available");
}

export function importPlaylist(playlistId: string) {
  return apiPost<PlaylistImportReport>("/api/playlists/import", {
    platform: "spotify",
    playlist_id: playlistId,
  });
}

export function listImportedPlaylists() {
  return apiGet<Playlist[]>("/api/playlists");
}

export function getPlaylist(id: number) {
  return apiGet<Playlist>(`/api/playlists/${id}`);
}

export function deletePlaylist(id: number) {
  return apiDelete<void>(`/api/playlists/${id}`);
}

export function playlistTracks(id: number) {
  return apiGet<Track[]>(`/api/playlists/${id}/tracks`);
}

export function syncPlaylist(id: number) {
  return apiPost<PlaylistImportReport>(`/api/playlists/${id}/sync`);
}

export interface LocalDirEntry {
  name: string;
  path: string;
  audio_file_count: number;
}

export interface LabelStats {
  label: string;
  track_count: number;
  artist_count: number;
  genres: string[];
  year_min: number | null;
  year_max: number | null;
}

export interface LabelBackfillReport {
  updated: number;
  candidates: number;
  remaining: number;
  rate_limited: boolean;
}

export function getLabels() {
  return apiGet<LabelStats[]>("/api/labels");
}

export function backfillLabels() {
  return apiPost<LabelBackfillReport>("/api/labels/backfill");
}

export function servicesStatus() {
  return apiGet<{ services: ServiceStatus[] }>("/api/services/status");
}

export function playlistGaps(id: number) {
  return apiGet<GapAnalysis>(`/api/playlists/${id}/gaps`);
}

export function libraryGaps() {
  return apiGet<GapAnalysis>("/api/playlists/library/gaps");
}

// --- Discovery (Fase F) -----------------------------------------------------

export function discoveryStatus() {
  return apiGet<DiscoveryStatus>("/api/discovery/status");
}

export function discoverExpand(playlistId: number, opts?: { limit?: number; use_ai?: boolean }) {
  return apiPost<DiscoveryResponse>("/api/discovery/expand", {
    playlist_id: playlistId,
    limit: opts?.limit,
    use_ai: opts?.use_ai,
  });
}

export function getDiscoveryGenres() {
  return apiGet<DiscoveryGenres>("/api/discovery/genres");
}

export function discoveryDig(
  seedType: "genre" | "label",
  value: string,
  opts?: { adventurousness?: number; limit?: number; tastePlaylistId?: number | null },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seed_type: seedType,
    value,
    adventurousness: opts?.adventurousness,
    limit: opts?.limit,
    taste_playlist_id: opts?.tastePlaylistId ?? null,
  });
}

export function discoveryAddLead(lead: DiscoveryLead) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/add", {
    artist: lead.artist,
    title: lead.title,
    album_art_url: lead.thumb_url,
  });
}

export function discoveryAddToLibrary(c: DiscoveryCandidate) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/add", {
    artist: c.artist,
    title: c.title,
    spotify_id: c.spotify_id,
    isrc: c.isrc,
    duration_seconds: c.duration_seconds,
    album_art_url: c.album_art_url,
    url: c.spotify_url,
  });
}

export interface PlaylistAddTrackResult {
  created: boolean;
  track: Track;
  spotify_added: boolean;
  spotify_error: string | null;
}

export function addDiscoveredTrackToPlaylist(playlistId: number, c: DiscoveryCandidate) {
  return apiPost<PlaylistAddTrackResult>(`/api/playlists/${playlistId}/discovered-tracks`, {
    artist: c.artist,
    title: c.title,
    spotify_id: c.spotify_id,
    isrc: c.isrc,
    duration_seconds: c.duration_seconds,
    album_art_url: c.album_art_url,
    url: c.spotify_url,
  });
}

export function importManualPlaylist(name: string, text: string) {
  return apiPost<PlaylistImportReport>("/api/playlists/import-manual", { name, text });
}

// --- Shazam: identificazione set DJ (Fase 1) --------------------------------

export interface DjSetTrack {
  position: number;
  start_offset_seconds: number | null;
  artist: string | null;
  title: string | null;
  isrc: string | null;
  confidence: number | null;
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

export function shazamStatus() {
  return apiGet<{ available: boolean }>("/api/shazam/status");
}

export function identifyMix(url: string) {
  return apiPost<ShazamIdentifyState>("/api/shazam/identify", { url });
}

export function shazamIdentifyStatus() {
  return apiGet<ShazamIdentifyState>("/api/shazam/identify-status");
}

export function listDjSets() {
  return apiGet<DjSet[]>("/api/shazam/sets");
}

export function getDjSet(id: number) {
  return apiGet<DjSetDetail>(`/api/shazam/sets/${id}`);
}

export function deleteDjSet(id: number) {
  return apiDelete<void>(`/api/shazam/sets/${id}`);
}

// --- Enrichment feature musicali --------------------------------------------

export function enrichmentJobStatus() {
  return apiGet<FeatureEnrichJob>("/api/enrichment/features/status");
}

export function startEnrichment(force = false) {
  return apiPost<FeatureEnrichJob>(`/api/enrichment/features?force=${force}`);
}

/** Riesegue l'enrichment sulle sole tracce di una playlist (force: bypassa la cache). */
export function enrichPlaylist(playlistId: number) {
  return apiPost<FeatureEnrichJob>(`/api/playlists/${playlistId}/enrich`);
}

export function trackLabel(t: Track): string {
  const artist = t.artist?.trim() || "Artista sconosciuto";
  const title = t.title?.trim() || "Senza titolo";
  return `${artist} — ${title}`;
}

export function featureEnrichSummary(r: FeatureEnrichReport): string {
  const parts = [
    `${r.ready_for_set}/${r.total} pronte per il set`,
    `${r.with_bpm} con BPM`,
    `${r.with_key} con key`,
  ];
  if (r.enriched) parts.push(`${r.enriched} aggiornate`);
  if (r.metadata_enriched) parts.push(`${r.metadata_enriched} con metadati`);
  if (r.missing_core_features) parts.push(`${r.missing_core_features} senza BPM/key`);
  if (r.not_found) parts.push(`${r.not_found} non trovate`);
  return parts.join(" - ");
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

// --- Download (Soulseek/slskd) ----------------------------------------------

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

export type DownloadItem = {
  track_id: number;
  artist: string | null;
  title: string | null;
  outcome: "downloaded" | "needs_review" | "not_found" | "failed";
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
};

export function downloadStatus() {
  return apiGet<DownloadStatus>("/api/downloads/status");
}

export function downloadCandidates(artist: string, title: string, durationSeconds?: number | null) {
  // La durata attesa (se nota) premia nel ranking la versione giusta.
  return apiPost<DownloadCandidate[]>("/api/downloads/candidates",
    { artist, title, duration_seconds: durationSeconds ?? undefined });
}

export function startPlaylistDownload(playlistId: number) {
  return apiPost<DownloadStatus>(`/api/downloads/playlist/${playlistId}`);
}

export function downloadTrack(trackId: number, candidate: DownloadCandidate) {
  return apiPost<DownloadStatus>("/api/downloads/track", { track_id: trackId, candidate });
}

export function searchDownloads(query: string) {
  return apiPost<DownloadCandidate[]>("/api/downloads/search", { query });
}

export function downloadManual(candidate: DownloadCandidate) {
  return apiPost<DownloadStatus>("/api/downloads/manual", { candidate });
}
