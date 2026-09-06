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
const startAnalysis = vi.fn(async () => ({
  status: "running" as const, processed: 0, total: 0, analyzed: 0, failed: 0,
  applied: 0, current_label: null, error: null,
}));

vi.mock("@/lib/api", () => ({
  analysisStatus: (...a: unknown[]) => analysisStatus(...(a as [])),
  downloadStatus: (...a: unknown[]) => downloadStatus(...(a as [])),
  generateStatus: (...a: unknown[]) => generateStatus(...(a as [])),
  libraryIndexStatus: (...a: unknown[]) => libraryIndexStatus(...(a as [])),
  shazamIdentifyStatus: (...a: unknown[]) => shazamIdentifyStatus(...(a as [])),
  streamingImportStatus: (...a: unknown[]) => streamingImportStatus(...(a as [])),
  startAnalysis: (...a: unknown[]) => startAnalysis(...(a as [])),
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

/** Percorre la catena apply -> scan: apply in corso, poi concluso con `ops`
 *  operazioni applicate. Lascia il job di scansione fermo su idle. */
async function applyConcluso(ops: number) {
  applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 1, total: 3 });
  render(<JobsProvider><div /></JobsProvider>);
  await tick();
  applyStatus.mockResolvedValue({
    ...idleApply, status: "done", processed: 3, total: 3,
    result: { applied_ops: ops } as ApplyJobState["result"],
  });
  await tick(2000);
}

/** Porta il job di scansione da running all'esito indicato, un poll per stato. */
async function scansione(esito: "done" | "error") {
  libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: "running", processed: 1, total: 2 });
  await tick(2000);
  libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: esito });
  await tick(2000);
}

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

  it("a fine scansione innescata dall'apply parte l'analisi BPM/key", async () => {
    /* Terzo anello: apply -> scan -> analisi. Sta DOPO la scansione perche'
       l'apply sposta i file senza riscrivere i percorsi in DB. */
    await applyConcluso(3);
    expect(startScan).toHaveBeenCalledTimes(1);
    expect(startAnalysis).not.toHaveBeenCalled();

    await scansione("done");

    expect(startAnalysis).toHaveBeenCalledTimes(1);
    expect(startAnalysis).toHaveBeenCalledWith("missing");
  });

  it("ma una scansione manuale NON fa partire l'analisi", async () => {
    /* Il caso che distingue questo anello da un innesco incondizionato su
       ogni fine scansione: senza, l'analisi ripartirebbe a ogni scan. */
    render(<JobsProvider><div /></JobsProvider>);
    await tick();

    await scansione("done");

    expect(startAnalysis).not.toHaveBeenCalled();
  });

  it("se la scansione viene rifiutata l'analisi non parte", async () => {
    /* Scan gia' in corso (409) o backend offline: l'innesco non si arma, e la
       scansione che sta girando non e' quella che riallinea i file appena
       spostati. */
    startScan.mockRejectedValueOnce(new Error("409 scan_running"));
    await applyConcluso(3);
    expect(startScan).toHaveBeenCalledTimes(1);

    await scansione("done");

    expect(startAnalysis).not.toHaveBeenCalled();
  });

  it("una scansione finita in errore consuma comunque l'innesco", async () => {
    /* Niente analisi su un indice non riallineato; e l'innesco non deve
       sopravvivere per aggrapparsi alla prima scansione manuale successiva. */
    await applyConcluso(3);

    await scansione("error");
    expect(startAnalysis).not.toHaveBeenCalled();

    await scansione("done");
    expect(startAnalysis).not.toHaveBeenCalled();
  });

  it("un avvio dell'analisi rifiutato non rompe la barra dei job", async () => {
    /* Essentia non installato (503): l'apply e' concluso e riuscito, l'errore
       dell'anello opzionale non deve arrivare all'utente ne' alla barra. */
    startAnalysis.mockRejectedValueOnce(new Error("503 analysis_engine_unavailable"));
    await applyConcluso(3);
    await scansione("done");

    expect(startAnalysis).toHaveBeenCalledTimes(1);

    applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 2, total: 8 });
    await tick(2000);
    expect(screen.getByText("25%")).toBeTruthy();
  });
});
