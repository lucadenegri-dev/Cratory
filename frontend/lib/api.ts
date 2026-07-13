import { translateApiError } from "@/lib/i18n/runtime";

// Base API vuota = stesso host della pagina: le chiamate /api/* passano dal
// rewrite di next.config.ts verso il backend, quindi l'app funziona anche
// aperta da un altro dispositivo in LAN. NEXT_PUBLIC_API_URL resta come
// override opzionale solo per setup particolari (backend su origin diverso).
const API = process.env.NEXT_PUBLIC_API_URL ?? "";

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
  discogs_id: number | null;
  format_badge: string | null;
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

export const SPOTIFY_LOGIN_URL = `${API}/api/spotify/login`;

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

/** Modifica manuale di una traccia: i valori inseriti hanno la precedenza sull'enrichment. */
export function updateTrack(id: number, patch: TrackUpdate) {
  return apiPatch<TrackDetail>(`/api/tracks/${id}`, patch);
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

export async function analysisOverview() {
  return apiGet<AnalysisOverview>("/api/analysis/overview");
}

export async function startAnalysis(scope: "missing" | "all", trackIds?: number[]) {
  return apiPost<AnalysisJobStatus>("/api/analysis/start", {
    scope, track_ids: trackIds ?? null,
  });
}

export async function analysisStatus() {
  return apiGet<AnalysisJobStatus>("/api/analysis/status");
}

export async function analysisDivergences() {
  return apiGet<AnalysisDivergence[]>("/api/analysis/divergences");
}

export async function applyAnalysis(body: {
  track_ids?: number[]; mode?: "divergent" | "all"; force?: boolean;
}) {
  return apiPost<{ applied: number; skipped: number }>("/api/analysis/apply", body);
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

/** Stato della generazione set in background: unico poller in JobsProvider. */
export function generateStatus() {
  return apiGet<GenStatus>("/api/sets/generate-status");
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

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      if (d && typeof d === "object" && !Array.isArray(d) && typeof d.code === "string") {
        detail = translateApiError(d.code, d.params ?? {}, d.message ?? res.statusText);
      } else {
        detail = typeof d === "string" ? d : JSON.stringify(d);
      }
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  // Niente `new URL(...)`: con base relativa (API vuota) lancerebbe. La query
  // string viene costruita a mano, così l'URL resta relativo allo stesso host.
  let url = API + path;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  return handle<T>(await fetch(url));
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiSend<T>("POST", path, body);
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return apiSend<T>("PATCH", path, body);
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return apiSend<T>("PUT", path, body ?? {});
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

/** Upload multipart: niente header Content-Type manuale, lo imposta fetch col boundary. */
export async function apiUpload<T>(path: string, body: FormData): Promise<T> {
  return handle<T>(await fetch(API + path, { method: "POST", body }));
}

export async function exportSet(setId: number, format: "text" | "csv" | "markdown" | "m3u8"): Promise<string> {
  const res = await fetch(`${API}/api/sets/${setId}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

/** Aggiunge una traccia al set (A14): position 1-based, assente = append in coda. */
export function addTrackToSet(setId: number, trackId: number, position?: number) {
  return apiPost<Setlist>(`/api/sets/${setId}/tracks`, { track_id: trackId, position });
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

export interface LikedTrackPreview {
  spotify_id: string;
  isrc: string | null;
  title: string | null;
  artist: string | null;
  duration_seconds: number | null;
  artwork_url: string | null;
  already_imported: boolean;
}

/** Anteprima dei liked Spotify: non importa nulla, marca i già presenti in libreria. */
export function previewLikedTracks() {
  return apiGet<LikedTrackPreview[]>("/api/playlists/spotify/liked/preview");
}

/** Importa nella playlist "Spotify Likes" solo i brani selezionati (additivo). */
export function importSelectedLikedTracks(spotifyIds: string[]) {
  return apiPost<PlaylistImportReport>("/api/playlists/import/liked/selected", {
    spotify_ids: spotifyIds,
  });
}

// --- SoundCloud ---------------------------------------------------------------

export interface SoundCloudStatus {
  available: boolean;
  ytdlp_version: string | null;
  username: string | null;
}

export function soundcloudStatus() {
  return apiGet<SoundCloudStatus>("/api/soundcloud/status");
}

export function setSoundcloudUsername(username: string) {
  return apiPut<SoundCloudStatus>("/api/soundcloud/config", { username });
}

/** Importa una playlist SoundCloud da URL (pubblica o secret link). Solo metadati. */
export function importSoundcloudPlaylist(url: string) {
  return apiPost<PlaylistImportReport>("/api/soundcloud/import", { url });
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

/** Anteprima di TUTTI i like SoundCloud: non importa nulla (nessun cap). */
export function previewSoundcloudLikes() {
  return apiGet<SoundCloudLikedTrackPreview[]>("/api/soundcloud/likes/preview");
}

/** Importa nella playlist "SoundCloud Likes" solo i brani selezionati (additivo). */
export function importSelectedSoundcloudLikes(trackIds: string[]) {
  return apiPost<PlaylistImportReport>("/api/soundcloud/import/likes", { track_ids: trackIds });
}

export function listImportedPlaylists() {
  return apiGet<Playlist[]>("/api/playlists");
}

export function getPlaylist(id: number) {
  return apiGet<Playlist>(`/api/playlists/${id}`);
}

export interface PlaylistDeleteResult {
  deleted_tracks: number;
}

/** Sorgente cover di una traccia: Spotify se presente, altrimenti l'artwork
 *  embedded nel file (endpoint on-demand) per le possedute, altrimenti nessuna. */
export function trackCoverSrc(
  t: { id: number; album_art_url?: string | null; has_local_file?: boolean | null },
): string | null {
  if (t.album_art_url) return t.album_art_url;
  if (t.has_local_file) return `${API}/api/tracks/${t.id}/cover`;
  return null;
}

export function deletePlaylist(id: number) {
  return apiDelete<PlaylistDeleteResult>(`/api/playlists/${id}`);
}

export function playlistTracks(id: number) {
  return apiGet<Track[]>(`/api/playlists/${id}/tracks`);
}

export function syncPlaylist(id: number) {
  return apiPost<PlaylistImportReport>(`/api/playlists/${id}/sync`);
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

export function getLabels() {
  return apiGet<LabelStats[]>("/api/labels");
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

export interface DiscogsTrack {
  position: string;
  title: string;
  duration_seconds: number | null;
}

export interface DiscogsRelease {
  discogs_id: number;
  title: string;
  artist: string;
  thumb_url: string | null;
  discogs_url: string | null;
  year: number | null;
  label: string | null;
  tracks: DiscogsTrack[];
}

export function getDiscogsRelease(discogsId: number) {
  return apiGet<DiscogsRelease>(`/api/discovery/release/${discogsId}`);
}

export interface DiscoveryImportInput {
  artist: string;
  title: string;
  duration_seconds?: number | null;
  album_art_url?: string | null;
  url?: string | null;
}

export function discoveryImportTrack(input: DiscoveryImportInput) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/add", input);
}

export function discoverySaveForLater(input: DiscoveryImportInput) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/save-for-later", input);
}

export function downloadTrackAuto(trackId: number) {
  return apiPost<DownloadStatus>("/api/downloads/track/auto", { track_id: trackId });
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

export function createPlaylistFromTracks(name: string, trackIds: number[]) {
  return apiPost<Playlist>("/api/playlists/create-from-tracks", { name, track_ids: trackIds });
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

/** Promuove le tracce identificate del set a lead in una playlist 'manual'. */
export function importDjSetAsPlaylist(id: number) {
  return apiPost<PlaylistImportReport>(`/api/shazam/sets/${id}/import-playlist`);
}

export function deleteDjSet(id: number) {
  return apiDelete<void>(`/api/shazam/sets/${id}`);
}

export function trackLabel(t: Track): string {
  const artist = t.artist?.trim() || "Artista sconosciuto";
  const title = t.title?.trim() || "Senza titolo";
  return `${artist} — ${title}`;
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

export function downloadPending() {
  return apiGet<Track[]>("/api/downloads/pending");
}

export function retryPending() {
  return apiPost<DownloadStatus>("/api/downloads/retry-pending");
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

/** "Ignora": azzera l'esito download, la traccia esce dall'archivio da sistemare. */
export function ignoreDownload(trackId: number) {
  return apiDelete<Track>(`/api/downloads/pending/${trackId}`);
}

// --- File locali (collegamento manuale) ---------------------------------------

export interface LocalFileHit {
  path: string;
  name: string;
  format: string | null;
  size: number | null;
  source: "library" | "downloads";
}

/** Cerca file audio per nome in LIBRARY_ROOT e nella cartella download slskd. */
export function searchLocalFiles(q: string) {
  return apiGet<LocalFileHit[]>("/api/files/search", { q });
}

/** Collega manualmente un file su disco alla traccia (possesso senza download). */
export function linkLocalFile(trackId: number, path: string) {
  return apiPost<TrackDetail>(`/api/tracks/${trackId}/link-file`, { path });
}

// --- Revisione file dubbio (needs_review-per-durata) --------------------------

export type DownloadReview = {
  expected: { artist: string | null; title: string | null; duration_seconds: number | null };
  downloaded: {
    path: string; name: string; format: string | null; bitrate: number | null;
    duration_seconds: number | null; size: number | null;
  } | null;
  reason: string | null;
};

/** Atteso vs file già scaricato per una traccia da rivedere. */
export function downloadReview(trackId: number) {
  return apiGet<DownloadReview>(`/api/downloads/review/${trackId}`);
}

/** Tieni il file dubbio: lo aggancia come possesso e svuota l'esito. */
export function keepReview(trackId: number) {
  return apiPost<Track>("/api/downloads/keep-review", { track_id: trackId });
}

/** Scarta il file dubbio: lo elimina dall'inbox e sgancia la traccia. */
export function discardReview(trackId: number) {
  return apiPost<Track>("/api/downloads/discard-review", { track_id: trackId });
}

// --- Auto-collega file locale su tutte le da sistemare ------------------------

export type AutoLinkProposal = {
  track_id: number;
  label: string;
  artist: string | null;
  title: string | null;
  hit: { path: string; name: string; format: string | null; size: number | null; source: "library" | "downloads" } | null;
};

/** Per ogni traccia da sistemare, il miglior file locale che combacia (o null). Non collega. */
export function autoLinkPreview() {
  return apiGet<AutoLinkProposal[]>("/api/downloads/auto-link");
}

// --- Rekordbox (import collezione XML) --------------------------------------

export interface RekordboxImportReport {
  in_file: number;
  matched: number;
  unmatched: number;
  bpm_set: number;
  key_set: number;
  energy_set: number;
}

export async function importRekordbox(file: File, overwrite = false) {
  const fd = new FormData();
  fd.append("file", file);
  return apiUpload<RekordboxImportReport>(
    `/api/rekordbox/import${overwrite ? "?overwrite=true" : ""}`, fd,
  );
}
