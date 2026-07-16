import { apiGet, apiPost } from "./client";
import type {
  DiscogsRelease,
  DiscoveryAddResponse,
  DiscoveryDigResponse,
  DiscoveryGenres,
  DiscoveryImportInput,
  DiscoveryPreview,
  DiscoveryResponse,
  DiscoveryStatus,
} from "./types";

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

// Rispecchia SEARCH_PER_PAGE del backend (il massimo per pagina di Discogs).
// Serve alla UI per calcolare quante release sono raggiungibili
// (pile_pages × DISCOGS_PAGE_SIZE) senza cablare "10.000" nel testo.
export const DISCOGS_PAGE_SIZE = 100;

export function discoveryDig(
  seedType: "genre" | "label",
  value: string,
  opts?: { depth?: number },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seed_type: seedType,
    value,
    depth: opts?.depth,
  });
}

export function getDiscogsRelease(discogsId: number) {
  return apiGet<DiscogsRelease>(`/api/discovery/release/${discogsId}`);
}

export function discoveryPreview(input: {
  artist: string;
  title: string;
  discogsId?: number | null;
  level?: "release" | "track";
}) {
  return apiGet<DiscoveryPreview>("/api/discovery/preview", {
    artist: input.artist,
    title: input.title,
    discogs_id: input.discogsId ?? undefined,
    level: input.level ?? "track",
  });
}

export function discoveryImportTrack(input: DiscoveryImportInput) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/add", input);
}

export function discoverySaveForLater(input: DiscoveryImportInput) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/save-for-later", input);
}
