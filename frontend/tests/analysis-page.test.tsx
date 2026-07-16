import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AnalysisPage from "@/app/analysis/page";
import type { AnalysisDivergence, AnalysisOverview } from "@/lib/api";

/* Il ridisegno della pagina Analisi poggia su regole di sicurezza che non si
   vedono a schermo finche' non esistono divergenze reali (in esercizio
   divergent=0 e' lo stato stazionario). Qui le divergenze sono finte, cosi' i
   guard restano verificati anche quando la libreria e' pulita. */

const applyAnalysis = vi.fn();
const startAnalysis = vi.fn();
const analysisOverview = vi.fn();
const analysisDivergences = vi.fn();

vi.mock("@/lib/api", () => ({
  analysisOverview: (...a: unknown[]) => analysisOverview(...a),
  analysisDivergences: (...a: unknown[]) => analysisDivergences(...a),
  applyAnalysis: (...a: unknown[]) => applyAnalysis(...a),
  startAnalysis: (...a: unknown[]) => startAnalysis(...a),
  errText: (e: unknown) => String((e as Error)?.message ?? e),
}));

vi.mock("@/components/jobs-provider", () => ({
  useJobs: () => ({ analysis: null, refresh: vi.fn() }),
}));

// La card Rekordbox ha un suo import client: fuori dallo scope di questi test.
vi.mock("@/components/analysis/rekordbox-import-card", () => ({
  RekordboxImportCard: () => <div data-testid="rekordbox-card" />,
}));

const OVERVIEW: AnalysisOverview = {
  owned: 412, ready_for_set: 411, missing_bpm: 1, missing_key: 1,
  bpm_by_source: { manual: 0, rekordbox: 355, cratory: 56 },
  key_by_source: { manual: 0, rekordbox: 355, cratory: 56 },
  analyzed: 57, divergent: 0, rekordbox_pending: 1,
} as AnalysisOverview;

/** Divergenza con BPM da Rekordbox ma key corretta a mano: e' il caso che la
 *  vecchia cella nascondeva mostrando una sola fonte per due valori. */
const MIXED: AnalysisDivergence = {
  track_id: 1, artist: "Floating Points", title: "Silhouettes",
  bpm: 124, camelot_key: "8A", bpm_source: "rekordbox", key_source: "manual",
  analysis_bpm: 128, analysis_camelot: "9A", bpm_delta: 4, key_compatibility: "weak",
} as AnalysisDivergence;

/** Divergenza senza autorita' da proteggere: applicabile senza conferma. */
const CRATORY_ONLY: AnalysisDivergence = {
  track_id: 2, artist: "Objekt", title: "Ganzfeld",
  bpm: 130, camelot_key: "5A", bpm_source: "cratory", key_source: "cratory",
  analysis_bpm: 130.5, analysis_camelot: "5A", bpm_delta: 0.5, key_compatibility: "same",
} as AnalysisDivergence;

function mount(divergences: AnalysisDivergence[], overview: Partial<AnalysisOverview> = {}) {
  analysisOverview.mockResolvedValue({ ...OVERVIEW, ...overview });
  analysisDivergences.mockResolvedValue(divergences);
  return render(<AnalysisPage />);
}

describe("pagina Analisi", () => {
  beforeEach(() => {
    applyAnalysis.mockReset().mockResolvedValue({ applied: 1, skipped: 0 });
    startAnalysis.mockReset().mockResolvedValue({});
    analysisOverview.mockReset();
    analysisDivergences.mockReset();
  });
  afterEach(cleanup);

  it("senza divergenze non arma il force: niente bottone da premere a vuoto", async () => {
    mount([]);
    await screen.findByText(/nessuna divergenza/i);
    // Prima il force era gated su `analyzed`, non su `divergent`: con analyzed=57
    // e divergent=0 restava rosso, vivo e garantito no-op.
    expect(screen.queryByRole("button", { name: /forza su tutte/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /applica tutte le divergenti/i })).toBeNull();
  });

  it("applica tutte le divergenti usa mode='divergent', non il force su tutte", async () => {
    mount([CRATORY_ONLY], { divergent: 1 });
    const btn = await screen.findByRole("button", { name: /applica tutte le divergenti \(1\)/i });
    btn.click();
    // mode:'divergent' esiste nel backend da sempre e non era mai stato chiamato.
    await waitFor(() => expect(applyAnalysis).toHaveBeenCalledWith({ mode: "divergent" }));
  });

  it("chiede conferma prima di calpestare una correzione manuale", async () => {
    mount([MIXED], { divergent: 1 });
    const btn = await screen.findByRole("button", { name: /applica tutte le divergenti/i });
    btn.click();
    // Il router tratta mode='divergent' come scelta esplicita e NON protegge i
    // manuali: la guardia deve imporla il frontend, come per le selezionate.
    await screen.findByRole("dialog");
    expect(applyAnalysis).not.toHaveBeenCalled();
  });

  it("applica senza conferma quando non c'e' autorita' da proteggere", async () => {
    mount([CRATORY_ONLY], { divergent: 1 });
    const btn = await screen.findByRole("button", { name: /applica tutte le divergenti/i });
    btn.click();
    await waitFor(() => expect(applyAnalysis).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("mostra la provenienza di BPM e key separatamente", async () => {
    mount([MIXED], { divergent: 1 });
    const row = (await screen.findByText(/Floating Points/)).closest("tr")!;
    // Una sola etichetta per due valori nascondeva che la key era manuale.
    expect(within(row).getByText(/\(rekordbox\)/)).toBeTruthy();
    expect(within(row).getByText(/\(manuale\)/)).toBeTruthy();
  });

  it("la descrizione dell'analisi segue lo scope: le due voci non fanno la stessa cosa", async () => {
    mount([]);
    // scope=missing analizza solo le non pronte; scope=all rianalizza tutto.
    // Una didascalia unica per entrambi direbbe il falso su almeno una delle due.
    await screen.findByText(/analizza l'unica traccia senza BPM o tonalità/i);
    expect(screen.queryByText(/rianalizza tutte le 412/i)).toBeNull();

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "all" } });

    await screen.findByText(/rianalizza tutte le 412 tracce possedute/i);
    expect(screen.queryByText(/analizza l'unica traccia/i)).toBeNull();
  });

  it("tace sulle divergenze da scope=missing quando non possono nascere", async () => {
    // missing_bpm=1, missing_key=1, pending=1 => l'unica non pronta manca di
    // ENTRAMBI i campi: non c'e' nulla da contraddire, e dirlo sarebbe rumore.
    mount([]);
    await screen.findByText(/riempie solo ciò che è vuoto/i);
    expect(screen.queryByText(/compare in Divergenze/i)).toBeNull();
  });

  it("avverte delle divergenze da scope=missing quando una traccia ha già l'altro campo", async () => {
    // missing_bpm=2, missing_key=1, pending=2 => 2*2-2-1 = 1 traccia a cui manca
    // un campo su due: il job scrive comunque entrambi gli analysis_*, quindi
    // il campo presente puo' essere contraddetto anche con scope=missing.
    mount([], { missing_bpm: 2, missing_key: 1, rekordbox_pending: 2, ready_for_set: 410 });
    await screen.findByText(/di queste, 1 ha già l'altro campo/i);
    expect(screen.getByText(/compare in Divergenze/i)).toBeTruthy();
  });

  it("non dichiara 100% di copertura con una traccia ancora non pronta", async () => {
    mount([]);
    // 411/412 = 99,75: Math.round diceva "100%" sopra l'unica cosa da fare.
    await screen.findByText(/411\/412 · 99%/);
    expect(screen.queryByText(/100%/)).toBeNull();
  });

  it("dichiara 100% solo quando tutte le possedute sono pronte", async () => {
    mount([], { owned: 412, ready_for_set: 412, missing_bpm: 0, missing_key: 0 });
    await screen.findByText(/411\/412 · 99%|412\/412 · 100%/);
    expect(screen.getByText(/412\/412 · 100%/)).toBeTruthy();
  });
});
