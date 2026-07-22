import { apiGet, apiPost } from "./client";
import type { DigSourceKey } from "../discovery-dig";
import type {
  DiscogsRelease,
  DiscoveryAddResponse,
  DiscoveryDigResponse,
  DiscoveryGenres,
  DiscoveryImportInput,
  DiscoveryPreview,
} from "./types";

export type { DigSourceKey };

// --- Discovery (Fase F) -----------------------------------------------------

export function getDiscoveryGenres() {
  return apiGet<DiscoveryGenres>("/api/discovery/genres");
}

export function discoveryDig(
  seedType: "genre" | "label",
  value: string,
  opts?: { depth?: number; source?: DigSourceKey },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seed_type: seedType,
    value,
    depth: opts?.depth,
    source: opts?.source,
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
