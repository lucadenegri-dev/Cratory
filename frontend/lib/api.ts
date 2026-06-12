const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Track {
  id: number;
  rekordbox_track_id: string;
  spotify_id: string | null;
  soundcloud_id: string | null;
  source_type: string;
  title: string | null;
  artist: string | null;
  album: string | null;
  genre: string | null;
  year: number | null;
  duration_seconds: number | null;
  bpm: number | null;
  tonality: string | null;
  play_count: number;
  cue_count: number;
  has_beatgrid: boolean;
  spotify_url: string | null;
  album_art_url: string | null;
  enriched: boolean;
}

export interface SpotifyStatus {
  configured: boolean;
  user_connected: boolean;
}

export interface EnrichReport {
  enriched: number;
  not_found: number;
  artists_updated: number;
  skipped_already_enriched: boolean;
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
  track: Track;
  transition_score: number | null;
  transition_reason: string | null;
  ai_reason: string | null;
  risk_level: string | null;
}

export interface Setlist {
  id: number;
  name: string;
  strategy: string | null;
  target_duration_minutes: number | null;
  global_explanation: string | null;
  total_duration_seconds: number;
  tracks: SetlistTrack[];
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
  last_import: { id: number; stats: Record<string, unknown>; created_at: string } | null;
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
  return handle<T>(
    await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export async function uploadXml(file: File) {
  const form = new FormData();
  form.append("file", file);
  return handle<{ id: number; stats: Record<string, unknown>; errors: string[] }>(
    await fetch(`${API}/api/import/rekordbox-xml`, { method: "POST", body: form }),
  );
}

export async function exportSet(setId: number, format: "text" | "csv"): Promise<string> {
  const res = await fetch(`${API}/api/sets/${setId}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

export function trackLabel(t: Track): string {
  const title = t.title ?? (t.spotify_id ? `[Spotify ${t.spotify_id.slice(0, 8)}…]` : t.rekordbox_track_id);
  return `${t.artist ?? "?"} — ${title}`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
