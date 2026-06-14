const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Track {
  id: number;
  rekordbox_track_id: string | null;
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
  tonality: string | null;
  camelot_key: string | null;
  mood: string | null;
  energy: number | null;
  danceability: number | null;
  vocalness: number | null;
  label: string | null;
  play_count: number;
  status: string;
  url: string | null;
  isrc: string | null;
  playlist_name: string | null;
  cue_count: number;
  has_beatgrid: boolean;
  spotify_url: string | null;
  album_art_url: string | null;
  enriched: boolean;
  enrichment_source: string | null;
  enrichment_confidence: number | null;
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

export interface EnrichReport {
  enriched: number;
  not_found: number;
  artists_updated: number;
  skipped_already_enriched: boolean;
}

export interface EnrichJobStatus {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: EnrichReport | null;
  error: string | null;
}

export interface FeatureProviderStatus {
  configured: boolean;
  provider: string | null;
}

export interface FeatureEnrichReport {
  enriched: number;
  not_found: number;
  total: number;
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

export interface TrackDetail extends Track {
  comments: string | null;
  location: string | null;
  cue_points: { name: string | null; type: string | null; start_seconds: number }[];
  beatgrid_bpms: number[];
}

export interface TransitionScore {
  score: number;
  technical_reasons: string[];
  warnings: string[];
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
  validation: SetlistValidation;
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

export interface LibraryStats {
  total_tracks: number;
  by_source: Record<string, number>;
  with_bpm: number;
  with_tonality: number;
  with_cues: number;
  missing_metadata: number;
  bpm_min: number | null;
  bpm_max: number | null;
  key_distribution: Record<string, number>;
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

export function playlistTracks(id: number) {
  return apiGet<Track[]>(`/api/playlists/${id}/tracks`);
}

export function playlistGaps(id: number) {
  return apiGet<GapAnalysis>(`/api/playlists/${id}/gaps`);
}

export function libraryGaps() {
  return apiGet<GapAnalysis>("/api/playlists/library/gaps");
}

export function trackLabel(t: Track): string {
  const fallback = t.spotify_id ? `[Spotify ${t.spotify_id.slice(0, 8)}…]` : `#${t.id}`;
  return `${t.artist ?? "?"} — ${t.title ?? fallback}`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
