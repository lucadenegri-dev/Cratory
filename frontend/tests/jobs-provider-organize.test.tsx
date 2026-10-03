import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { JobsProvider, useJobs } from "@/components/jobs-provider";
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
// Gli avvii rispondono come il backend: lo snapshot del job appena partito,
// con il suo `started_at` — e' cio' che il provider usa per riconoscerlo.
const startScan = vi.fn(async () => ({ ...idleLibraryIndex, status: "running" as const, started_at: "S1" }));
const apiStartApply = vi.fn(async () => ({ ...idleApply, status: "running" as const, started_at: "A1" }));
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
  startApply: (...a: unknown[]) => apiStartApply(...(a as [])),
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

/** Porta il job di scansione da running all'esito indicato, un poll per stato.
 *  `avvio` e' il suo `started_at`: di default quello della scansione che la
 *  catena lancia (S1, vedi il mock di `startScan`). */
async function scansione(esito: "done" | "error", avvio = "S1") {
  libraryIndexStatus.mockResolvedValue({
    ...idleLibraryIndex, status: "running", processed: 1, total: 2, started_at: avvio,
  });
  await tick(2000);
  libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: esito, started_at: avvio });
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

  it("riparte la scansione anche se l'apply finisce prima del primo poll", async () => {
    /* Un piano di poche operazioni dura millisecondi: il poll che segue
       l'avvio lo trova gia' `done`, e il provider non lo vede mai `running`.
       Riprodotto dal vero con un piano di 3 spostamenti (8 ms). */
    let avvia: () => Promise<void> = async () => {};
    function Avvio() { avvia = useJobs().startApply; return null; }
    render(<JobsProvider><Avvio /></JobsProvider>);
    await tick();

    applyStatus.mockResolvedValue({
      ...idleApply, status: "done", processed: 3, total: 3, started_at: "A1",
      result: { applied_ops: 3 } as ApplyJobState["result"],
    });
    await act(async () => { await avvia(); });
    await tick();

    expect(startScan).toHaveBeenCalledTimes(1);
  });

  it("ma l'esito dell'apply PRECEDENTE letto dopo l'avvio non conta", async () => {
    /* Un poll partito prima del POST puo' rispondere dopo: riporta ancora il
       `done` del giro prima (A0), non del nostro (A1). Scambiarlo per il
       nostro riscansionerebbe con l'apply ancora in corso. Un oggetto nuovo
       a ogni poll, come dalla rete: con lo stesso riferimento React non
       rirenderebbe e il test passerebbe senza guardare nulla. */
    applyStatus.mockImplementation(async () => ({
      ...idleApply, status: "done", processed: 3, total: 3, started_at: "A0",
      result: { applied_ops: 3 } as ApplyJobState["result"],
    }));
    let avvia: () => Promise<void> = async () => {};
    function Avvio() { avvia = useJobs().startApply; return null; }
    render(<JobsProvider><Avvio /></JobsProvider>);
    await tick();

    await act(async () => { await avvia(); });
    await tick();

    expect(startScan).not.toHaveBeenCalled();
  });

  it("applyDellaSessione e' solo l'apply concluso in questa sessione", async () => {
    /* La pagina Plan ci appoggia lo svuotamento del draft e i banner: un
       `done` della sessione precedente non deve contare, quello lanciato da
       qui si'. */
    applyStatus.mockImplementation(async () => ({
      ...idleApply, status: "done", processed: 3, total: 3, started_at: "A0",
      result: { applied_ops: 3 } as ApplyJobState["result"],
    }));
    let api: ReturnType<typeof useJobs> | null = null;
    function Spia() { api = useJobs(); return null; }
    render(<JobsProvider><Spia /></JobsProvider>);
    await tick();
    expect(api!.applyDellaSessione).toBeNull();

    applyStatus.mockImplementation(async () => ({
      ...idleApply, status: "done", processed: 3, total: 3, started_at: "A1",
      result: { applied_ops: 3 } as ApplyJobState["result"],
    }));
    await act(async () => { await api!.startApply(); });
    await tick();
    expect(api!.applyDellaSessione).toBe("A1");
  });

  it("ma un apply gia' concluso trovato all'apertura NON fa ripartire nulla", async () => {
    /* Lo stato del job vive in memoria nel backend fino al prossimo apply:
       aprire l'app dopo un apply lo trova `done`. Non e' un apply di questa
       sessione, e non deve riscansionare. */
    applyStatus.mockResolvedValue({
      ...idleApply, status: "done", processed: 3, total: 3, started_at: "A0",
      result: { applied_ops: 3 } as ApplyJobState["result"],
    });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();
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

  it("parte l'analisi anche se la scansione finisce prima del primo poll", async () => {
    /* Stessa corsa del primo anello, sul secondo: su una libreria piccola la
       scansione dura meno di un poll e il provider la trova gia' conclusa. */
    await applyConcluso(3);
    expect(startScan).toHaveBeenCalledTimes(1);

    libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: "done", started_at: "S1" });
    await tick(2000);

    expect(startAnalysis).toHaveBeenCalledTimes(1);
    expect(startAnalysis).toHaveBeenCalledWith("missing");
  });

  it("ma una scansione vecchia gia' conclusa NON fa partire l'analisi", async () => {
    /* Il rovescio: dopo l'apply, un poll partito prima dell'avvio puo'
       riportare l'esito della scansione PRECEDENTE. Non e' la nostra. */
    await applyConcluso(3);

    libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: "done", started_at: "S0" });
    await tick(2000);

    expect(startAnalysis).not.toHaveBeenCalled();
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
