import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { JobsProvider } from "@/components/jobs-provider";
import type {
  AnalysisJobStatus, DownloadStatus, GenStatus, LibraryIndexJob, ShazamIdentifyState,
  StreamingImportJobStatus,
} from "@/lib/api";
import type { ApplyJobState, GenreReviewJobState, IntegrityJobState, ProviderRescanJobState } from "@/lib/organize/api";

/**
 * I job Organize dentro il provider unico. Il caso che conta è il riavvio
 * automatico della scansione a fine Apply: è un comportamento, non un'API, e
 * nessun tipo lo protegge — un grep sul sorgente non basterebbe, perché
 * sopravviverebbe alla riga commentata.
 */

const analysisStatus = vi.fn<() => Promise<AnalysisJobStatus>>();
const downloadStatus = vi.fn<() => Promise<DownloadStatus>>();
const generateStatus = vi.fn<() => Promise<GenStatus>>();
const libraryIndexStatus = vi.fn<() => Promise<LibraryIndexJob>>();
const shazamIdentifyStatus = vi.fn<() => Promise<ShazamIdentifyState>>();
const streamingImportStatus = vi.fn<() => Promise<StreamingImportJobStatus>>();

const applyStatus = vi.fn<() => Promise<ApplyJobState>>();
const providerRescanStatus = vi.fn<() => Promise<ProviderRescanJobState>>();
const integrityStatus = vi.fn<() => Promise<IntegrityJobState>>();
const genreReviewStatus = vi.fn<() => Promise<GenreReviewJobState>>();
const startScan = vi.fn(async () => idleApply);

vi.mock("@/lib/api", () => ({
  analysisStatus: (...a: unknown[]) => analysisStatus(...(a as [])),
  downloadStatus: (...a: unknown[]) => downloadStatus(...(a as [])),
  generateStatus: (...a: unknown[]) => generateStatus(...(a as [])),
  libraryIndexStatus: (...a: unknown[]) => libraryIndexStatus(...(a as [])),
  shazamIdentifyStatus: (...a: unknown[]) => shazamIdentifyStatus(...(a as [])),
  streamingImportStatus: (...a: unknown[]) => streamingImportStatus(...(a as [])),
}));

vi.mock("@/lib/organize/api", () => ({
  applyStatus: (...a: unknown[]) => applyStatus(...(a as [])),
  providerRescanStatus: (...a: unknown[]) => providerRescanStatus(...(a as [])),
  integrityStatus: (...a: unknown[]) => integrityStatus(...(a as [])),
  genreReviewStatus: (...a: unknown[]) => genreReviewStatus(...(a as [])),
  startScan: (...a: unknown[]) => startScan(...(a as [])),
  startApply: vi.fn(),
  providerRescan: vi.fn(),
  integrityCheck: vi.fn(),
  genreReview: vi.fn(),
}));

const idleApply: ApplyJobState = {
  status: "idle", phase: null, processed: 0, total: 0, result: null, error: null,
  started_at: null, finished_at: null,
};
const idleLibraryIndex: LibraryIndexJob = {
  status: "idle", phase: null, processed: 0, total: 0, result: null, error: null,
  started_at: null, finished_at: null,
};

function resetToIdle() {
  analysisStatus.mockResolvedValue({
    status: "idle", processed: 0, total: 0, analyzed: 0, failed: 0, applied: 0,
    current_label: null, error: null,
  });
  downloadStatus.mockResolvedValue({
    available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
    needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
    error: null, current_label: null,
  } as DownloadStatus);
  generateStatus.mockResolvedValue({ status: "idle", phase: null, error: null } as GenStatus);
  libraryIndexStatus.mockResolvedValue(idleLibraryIndex);
  shazamIdentifyStatus.mockResolvedValue({
    status: "idle", processed: 0, total: 0, phase: null, error: null,
  } as ShazamIdentifyState);
  streamingImportStatus.mockResolvedValue({
    status: "idle", processed: 0, total: 0, phase: null, error: null,
    current_label: null, result: null, sync_all: null,
  } as StreamingImportJobStatus);
  applyStatus.mockResolvedValue(idleApply);
  providerRescanStatus.mockResolvedValue(idleApply as ProviderRescanJobState);
  integrityStatus.mockResolvedValue({ ...idleApply, available: true } as IntegrityJobState);
  genreReviewStatus.mockResolvedValue(idleApply as GenreReviewJobState);
}

async function tick(ms = 0) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

beforeEach(() => {
  vi.useFakeTimers();
  resetToIdle();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("job Organize nel provider unico", () => {
  it("un apply in corso produce la sua riga", async () => {
    applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 2, total: 8 });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();
    expect(screen.getByText("25%")).toBeTruthy();
    expect(screen.getByText("2/8")).toBeTruthy();
  });

  it("la scansione produce UNA riga sola, non due", async () => {
    /* scan e libraryIndex sono lo stesso job da due endpoint: se il provider
       ne pollasse due, la barra mostrerebbe la stessa scansione due volte. */
    libraryIndexStatus.mockResolvedValue({
      ...idleLibraryIndex, status: "running", phase: "linking", processed: 5, total: 10,
    });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();
    expect(screen.getAllByText("50%")).toHaveLength(1);
    expect(screen.getByText("linking")).toBeTruthy();
  });

  it("a fine apply con operazioni applicate riparte la scansione", async () => {
    applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 1, total: 3 });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();
    expect(startScan).not.toHaveBeenCalled();

    applyStatus.mockResolvedValue({
      ...idleApply, status: "done", processed: 3, total: 3,
      result: { applied_ops: 3 } as ApplyJobState["result"],
    });
    await tick(2000);

    expect(startScan).toHaveBeenCalledTimes(1);
  });

  it("ma NON riparte se l'apply non ha applicato nulla", async () => {
    /* Il caso negativo: senza, il test precedente passerebbe anche con un
       riavvio incondizionato, che riscansionerebbe a vuoto a ogni apply. */
    applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 0, total: 0 });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();

    applyStatus.mockResolvedValue({
      ...idleApply, status: "done",
      result: { applied_ops: 0 } as ApplyJobState["result"],
    });
    await tick(2000);

    expect(startScan).not.toHaveBeenCalled();
  });
});
