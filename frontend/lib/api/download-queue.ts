import { apiDelete, apiGet, apiPost } from "./client";
import type { DownloadCandidate, QueueSnapshot } from "./types";

export function downloadQueue(opts?: { signal?: AbortSignal }) {
  return apiGet<QueueSnapshot>("/api/downloads/queue", undefined, opts);
}

/** Accoda un lotto. Il candidato vale solo con una traccia sola (lo impone il backend). */
export function enqueueDownloads(trackIds: number[],
                                 opts?: { kind?: string; candidate?: DownloadCandidate }) {
  return apiPost<{ enqueued: number; skipped: number }>("/api/downloads/queue", {
    track_ids: trackIds, kind: opts?.kind, candidate: opts?.candidate,
  });
}

export function cancelQueueItem(id: number) {
  return apiDelete<{ cancelled: boolean }>(`/api/downloads/queue/${id}`);
}

export function moveQueueItemTop(id: number) {
  return apiPost<{ moved: boolean }>(`/api/downloads/queue/${id}/top`);
}

export function cancelQueued() {
  return apiPost<{ cancelled: number }>("/api/downloads/queue/cancel-queued");
}

export function clearQueueDone() {
  return apiDelete<{ removed: number }>("/api/downloads/queue/done");
}
