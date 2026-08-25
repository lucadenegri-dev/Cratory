import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PrerequisitesStep } from "@/components/setup/steps/prerequisites";
import type { InstallStatus, ProbeComponent } from "@/lib/api";

const getProbe = vi.fn();
const startInstall = vi.fn();
const getInstallStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getProbe: (...a: unknown[]) => getProbe(...a),
  startInstall: (...a: unknown[]) => startInstall(...a),
  getInstallStatus: (...a: unknown[]) => getInstallStatus(...a),
}));

function comp(over: Partial<ProbeComponent>): ProbeComponent {
  return {
    key: "fpcalc", kind: "system", severity: "optional", present: false,
    version: null, source: null, shadowing: null, auto_installable: true, installable: true,
    install_method: "download", install_command: null, unlocks: [], docs: "https://esempio.invalid",
    ...over,
  };
}

/** Promise risolvibile dall'esterno: serve a bloccare un poll a piacere, così
 *  l'ordine delle chiamate si osserva senza dipendere dall'orologio reale. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

describe("PrerequisitesStep", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    startInstall.mockImplementation((key: string) =>
      Promise.resolve({ key, status: "running", log: [], detail: null }),
    );
    getInstallStatus.mockResolvedValue({ key: "fpcalc", status: "done", log: [], detail: null });
  });
  afterEach(cleanup);

  it("installa solo ciò che manca ed è installabile", async () => {
    // Qui c'era anche una voce slskd con `kind: "daemon"`, per provare che il
    // filtro escludesse i demoni. Non è più rappresentabile: slskd non è un
    // componente (lo sorveglia backend/tests/test_system_probe.py), e il
    // filtro non ha più un `kind` da guardare.
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "ffmpeg", present: false, installable: false }),
      comp({ key: "fpcalc", present: false, installable: true }),
    ]});
    render(<PrerequisitesStep />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);

    await waitFor(() => expect(startInstall).toHaveBeenCalledWith("fpcalc"));
    await waitFor(() => expect(startInstall).toHaveBeenCalledTimes(1));
    expect(startInstall).not.toHaveBeenCalledWith("ffmpeg");
    expect(startInstall).not.toHaveBeenCalledWith("slskd");
  });

  it("il bottone è spento quando non c'è niente da installare", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ present: true }),
    ]});
    render(<PrerequisitesStep />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    expect((bottone as HTMLButtonElement).disabled).toBe(true);
  });

  it("un componente mancante via ricetta fa comparire la nota di modifica al sistema (fix installer-sistema)", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "ffmpeg", present: false, installable: true, install_method: "recipe" }),
    ]});
    render(<PrerequisitesStep />);
    await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    // Frase specifica del bottone cumulativo (non quella, simile, della riga
    // sotto — entrambe compaiono insieme quando c'è un solo componente via
    // ricetta, e un pattern troppo largo becca entrambe).
    expect(screen.getByText(/alcuni di questi|some of these/i)).toBeTruthy();
  });

  it("senza nessun componente via ricetta, nessuna nota di modifica al sistema sul bottone cumulativo", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "fpcalc", present: false, installable: true, install_method: "download" }),
    ]});
    render(<PrerequisitesStep />);
    await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    expect(screen.queryByText(/alcuni di questi|some of these/i)).toBeNull();
  });

  it("installa in sequenza: il secondo non parte finché il primo non è finito (fix 3)", async () => {
    // Due componenti mancanti E installabili: con uno solo (come prima)
    // l'ordine non è osservabile, e l'asserzione varrebbe identica anche per
    // un'implementazione parallela. Il poll del primo resta appeso finché
    // non lo sblocchiamo noi: se il secondo `startInstall` parte comunque,
    // il giro non è sequenziale.
    const primoPoll = deferred<InstallStatus>();
    let pollCalls = 0;
    getInstallStatus.mockImplementation(() => {
      pollCalls += 1;
      if (pollCalls === 1) return primoPoll.promise;
      return Promise.resolve({ key: "essentia", status: "done", log: [], detail: null });
    });
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "fpcalc", present: false, installable: true }),
      comp({ key: "essentia", present: false, installable: true }),
    ]});
    render(<PrerequisitesStep />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);

    await waitFor(() => expect(startInstall).toHaveBeenCalledWith("fpcalc"));
    await waitFor(() => expect(pollCalls).toBeGreaterThan(0));
    // Il primo poll è ancora appeso: il secondo componente non deve essere partito.
    expect(startInstall).not.toHaveBeenCalledWith("essentia");

    primoPoll.resolve({ key: "fpcalc", status: "done", log: [], detail: null });
    await waitFor(() => expect(startInstall).toHaveBeenCalledWith("essentia"));
  });

  it("un componente fallito non blocca l'installazione degli altri (fix 1)", async () => {
    let pollCalls = 0;
    getInstallStatus.mockImplementation(() => {
      pollCalls += 1;
      if (pollCalls === 1) {
        return Promise.resolve({ key: "fpcalc", status: "error", log: [], detail: "python è uscito con codice 1" });
      }
      return Promise.resolve({ key: "essentia", status: "done", log: [], detail: null });
    });
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "fpcalc", present: false, installable: true }),
      comp({ key: "essentia", present: false, installable: true }),
    ]});
    render(<PrerequisitesStep />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);

    // Nonostante fpcalc fallisca, il giro prosegue con essentia.
    await waitFor(() => expect(startInstall).toHaveBeenCalledWith("essentia"));
    // E il fallimento non resta silenzioso: compare da qualche parte, col motivo.
    await waitFor(() => expect(screen.getByText(/python è uscito con codice 1/)).toBeTruthy());
  });

  it("un avvio fallito (409, rete) viene mostrato invece di sparire nel nulla (fix 1)", async () => {
    startInstall.mockRejectedValueOnce(new Error("409 Conflict"));
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "fpcalc", present: false, installable: true }),
    ]});
    render(<PrerequisitesStep />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);

    await waitFor(() => expect(screen.getByText(/409 Conflict/)).toBeTruthy());
    // Non essendoci mai stato un job avviato, non deve nemmeno iniziare il polling.
    expect(getInstallStatus).not.toHaveBeenCalled();
  });

  it("lo smontaggio dello step ferma il giro composito, non solo lo stato (fix 2)", async () => {
    const primoPoll = deferred<InstallStatus>();
    getInstallStatus.mockImplementation(() => primoPoll.promise);
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "fpcalc", present: false, installable: true }),
      comp({ key: "essentia", present: false, installable: true }),
    ]});
    const { unmount } = render(<PrerequisitesStep />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);
    await waitFor(() => expect(startInstall).toHaveBeenCalledWith("fpcalc"));

    // Simula la navigazione via a metà installazione (es. il bottone
    // Configura della riga demone, prima cliccabile a prescindere).
    unmount();
    // Se il primo poll si sblocca DOPO lo smontaggio, un giro che non si è
    // fermato proseguirebbe con essentia: non deve succedere.
    primoPoll.resolve({ key: "fpcalc", status: "done", log: [], detail: null });
    await new Promise((r) => setTimeout(r, 50));
    expect(startInstall).not.toHaveBeenCalledWith("essentia");
  });
});
