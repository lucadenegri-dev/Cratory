import { apiGet, apiPost } from "./client";
import type { AnalysisDivergence, AnalysisJobStatus, AnalysisOverview } from "./types";

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

export async function dismissAnalysis(trackIds: number[]) {
  return apiPost<{ dismissed: number }>("/api/analysis/dismiss", { track_ids: trackIds });
}
