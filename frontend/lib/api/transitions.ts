import { apiGet } from "./client";
import type { TransitionCandidate, TransitionClass } from "./types";

/** Tracce compatibili con `trackId`: lo score e' direzione-agnostico (BPM +
 *  tonalita' dominano), quindi non c'e' distinzione prima/dopo, un'unica lista. */
export function transitions(
  trackId: number | string,
  opts?: { limit?: number; lens?: TransitionClass; signal?: AbortSignal },
) {
  return apiGet<TransitionCandidate[]>(`/api/transitions/${trackId}`, {
    limit: opts?.limit,
    lens: opts?.lens,
  }, { signal: opts?.signal });
}
