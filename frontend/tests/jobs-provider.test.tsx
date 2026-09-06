import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { JobsProvider } from "@/components/jobs-provider";
import type {
  AnalysisJobStatus, DownloadStatus, GenStatus, LibraryIndexJob, ShazamIdentifyState,
  StreamingImportJobStatus,
} from "@/lib/api";

/**
 * Test della logica di merge del poller in JobsProvider (extract-if-needed:
 * la logica è inline nel provider, quindi qui la eserciziamo attraverso il
 * componente reale con i sei endpoint di stato mockati e timer finti — non
 * duplichiamo/estraiamo la funzione di merge fuori dal componente).
 */

const analysisStatus = vi.fn<() => Promise<AnalysisJobStatus>>();
const downloadStatus = vi.fn<() => Promise<DownloadStatus>>();
const generateStatus = vi.fn<() => Promise<GenStatus>>();
const libraryIndexStatus = vi.fn<() => Promise<LibraryIndexJob>>();
const shazamIdentifyStatus = vi.fn<() => Promise<ShazamIdentifyState>>();
const streamingImportStatus = vi.fn<() => Promise<StreamingImportJobStatus>>();

vi.mock("@/lib/api", () => ({
  analysisStatus: (...args: unknown[]) => analysisStatus(...(args as [])),
  downloadStatus: (...args: unknown[]) => downloadStatus(...(args as [])),
  generateStatus: (...args: unknown[]) => generateStatus(...(args as [])),
  libraryIndexStatus: (...args: unknown[]) => libraryIndexStatus(...(args as [])),
  shazamIdentifyStatus: (...args: unknown[]) => shazamIdentifyStatus(...(args as [])),
  streamingImportStatus: (...args: unknown[]) => streamingImportStatus(...(args as [])),
  startAnalysis: vi.fn(),
}));

const idleDownload: DownloadStatus = {
  available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
  needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
  error: null, current_label: null,
};
const idleLibraryIndex: LibraryIndexJob = {
  status: "idle", phase: null, processed: 0, total: 0, result: null, error: null,
  started_at: null, finished_at: null,
};
const idleAnalysis: AnalysisJobStatus = {
  status: "idle", processed: 0, total: 0, analyzed: 0, failed: 0, applied: 0,
  current_label: null, error: null,
};
const idleGeneration: GenStatus = {
  status: "idle", phase: null, using_ai: false, setlist_id: null, error: null,
};
const idleShazam: ShazamIdentifyState = {
  status: "idle", phase: null, processed: 0, total: 0, dj_set_id: null, error: null,
};
const idleStreamingImport: StreamingImportJobStatus = {
  status: "idle", kind: null, phase: null, processed: 0, total: 0, result: null,
  current_label: null, sync_all: null, error: null, error_code: null,
};

/** Riporta tutti e sei gli endpoint allo stato idle (nessun job attivo). */
function resetToIdle() {
  analysisStatus.mockResolvedValue(idleAnalysis);
  downloadStatus.mockResolvedValue(idleDownload);
  generateStatus.mockResolvedValue(idleGeneration);
  libraryIndexStatus.mockResolvedValue(idleLibraryIndex);
  shazamIdentifyStatus.mockResolvedValue(idleShazam);
  streamingImportStatus.mockResolvedValue(idleStreamingImport);
}

/** Avanza i timer finti e lascia risolvere le promise mockate (Promise.allSettled). */
async function tick(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
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

describe("JobsProvider — merge del poller", () => {
  it("mostra un job in corso con label e percentuale", async () => {
    downloadStatus.mockResolvedValue({
      ...idleDownload, status: "running", processed: 3, total: 10, current_label: "Artist — Title",
    });

    render(<JobsProvider><div /></JobsProvider>);
    await tick(); // flush del poll iniziale (start() chiama pollOnce() a mount)

    expect(screen.getByText("Download Soulseek")).toBeTruthy();
    expect(screen.getByText("Artist — Title")).toBeTruthy();
    expect(screen.getByText("30%")).toBeTruthy();
    expect(screen.getByText("3/10")).toBeTruthy();
  });

  it("alla transizione running -> done la riga esito resta visibile ~4s poi sparisce", async () => {
    downloadStatus.mockResolvedValue({
      ...idleDownload, status: "running", processed: 5, total: 10, current_label: "In corso",
    });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();
    expect(screen.getByText("Download Soulseek")).toBeTruthy();

    // Prossimo poll: il job è concluso con successo.
    downloadStatus.mockResolvedValue({
      ...idleDownload, status: "done", processed: 10, total: 10, downloaded: 10,
    });
    await tick(2000); // POLL_MS

    // La riga esito resta (outcome "done"): percentuale 100%, ancora presente.
    expect(screen.getByText("Download Soulseek")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();

    // Poco prima della scadenza (OUTCOME_MS = 4000) è ancora visibile.
    await tick(3000);
    expect(screen.getByText("Download Soulseek")).toBeTruthy();

    // Dopo la scadenza sparisce automaticamente (nessun altro job attivo).
    await tick(1500);
    expect(screen.queryByText("Download Soulseek")).toBeNull();
  });

  it("un esito di errore resta visibile finché non viene chiuso dall'utente", async () => {
    downloadStatus.mockResolvedValue({
      ...idleDownload, status: "running", processed: 1, total: 4, current_label: "In corso",
    });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();

    downloadStatus.mockResolvedValue({
      ...idleDownload, status: "error", processed: 1, total: 4, error: "Connessione persa",
    });
    await tick(2000);
    expect(screen.getByText("Connessione persa")).toBeTruthy();

    // Ben oltre OUTCOME_MS: un errore non si auto-rimuove.
    await tick(10_000);
    expect(screen.getByText("Connessione persa")).toBeTruthy();

    // L'utente lo chiude esplicitamente con la ✕ (aria-label "Chiudi").
    const dismiss = screen.getByLabelText("Chiudi");
    await act(async () => {
      dismiss.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(screen.queryByText("Connessione persa")).toBeNull();
  });

  it("il sync di massa mostra la playlist in corso e il riepilogo aggregato all'esito", async () => {
    streamingImportStatus.mockResolvedValue({
      ...idleStreamingImport, status: "running", kind: "playlists_sync_all",
      processed: 2, total: 5, current_label: "Techno 2026 · 45/120",
    });
    render(<JobsProvider><div /></JobsProvider>);
    await tick();

    expect(screen.getByText("Import playlist")).toBeTruthy();
    // `current_label` (playlist in corso col progresso interno) prevale sulla fase.
    expect(screen.getByText("Techno 2026 · 45/120")).toBeTruthy();

    // Prossimo poll: sync di massa concluso, con un fallimento. `result` è
    // valorizzato apposta con un report concorrente: se la priorità fosse
    // invertita la barra mostrerebbe "Residuo — 7 nuove" invece del riepilogo.
    streamingImportStatus.mockResolvedValue({
      ...idleStreamingImport, status: "done", kind: "playlists_sync_all",
      processed: 5, total: 5,
      result: {
        playlist_id: 3, name: "Residuo", created: 7, updated: 0,
        removed: 0, skipped: 0, total: 7,
      },
      sync_all: {
        synced: 4, failed: 1, created: 2, updated: 2, removed: 1, skipped: 0,
        failures: [{ playlist_id: 9, name: "Foo", platform: "spotify", error: "boom" }],
      },
    });
    await tick(2000); // POLL_MS

    // `sync_all` ha priorità su `result` per il riepilogo dell'esito.
    expect(screen.getByText("4 sincronizzate · 1 fallite")).toBeTruthy();
    expect(screen.queryByText("Residuo — 7 nuove")).toBeNull();
  });

  it("con la tab nascosta il polling si ferma e riprende al ritorno in foreground", async () => {
    render(<JobsProvider><div /></JobsProvider>);
    await tick(); // poll iniziale (mount, tab visibile)

    const callsAtStart = downloadStatus.mock.calls.length;
    expect(callsAtStart).toBeGreaterThan(0);

    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    const callsRightAfterHide = downloadStatus.mock.calls.length;

    // A tab nascosta, anche avanzando ben oltre POLL_MS, nessun nuovo poll.
    await tick(10_000);
    expect(downloadStatus.mock.calls.length).toBe(callsRightAfterHide);

    // Tornando visibile riparte subito un poll.
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await tick();
    expect(downloadStatus.mock.calls.length).toBeGreaterThan(callsRightAfterHide);
  });
});
