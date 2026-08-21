import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ComponentRow } from "@/components/setup/component-row";
import type { ProbeComponent } from "@/lib/api";

// Il mock deve esporre OGNI export usato dal componente: vitest solleva
// "No 'X' export is defined on the mock" al primo accesso mancante
// (stesso pattern di tests/credential-field.test.tsx).
const startInstall = vi.fn();
const getInstallStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  startInstall: (...a: unknown[]) => startInstall(...a),
  getInstallStatus: (...a: unknown[]) => getInstallStatus(...a),
}));

function comp(over: Partial<ProbeComponent>): ProbeComponent {
  return {
    key: "essentia",
    kind: "venv",
    severity: "optional",
    present: false,
    version: null,
    source: null,
    shadowing: null,
    auto_installable: true,
    installable: true,
    install_command: ["pip", "install", "essentia==2.1b6.dev1177"],
    unlocks: ["analysis_bpm_key"],
    docs: "https://essentia.upf.edu/installing.html",
    ...over,
  };
}

describe("ComponentRow", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("componente auto-installabile: niente comando manuale finché non fallisce", () => {
    render(<ComponentRow c={comp({})} onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: /installa|install/i })).toBeTruthy();
    expect(screen.queryByText(/pip install/)).toBeNull();
  });

  it("componente auto-installabile: un install fallito fa comparire il comando manuale (fix 1)", async () => {
    startInstall.mockResolvedValue({
      key: "essentia", status: "error", log: [], detail: "/x/python è uscito con codice 1",
    });
    getInstallStatus.mockResolvedValue({
      key: "essentia", status: "error", log: [], detail: "/x/python è uscito con codice 1",
    });
    render(<ComponentRow c={comp({})} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /installa|install/i }));

    // La ricetta manuale, prima assente, deve apparire dopo il fallimento.
    await waitFor(() => expect(screen.getByText(/pip install/)).toBeTruthy());
    // Riga tradotta in testa, dettaglio grezzo del backend come nota secondaria (fix 2c).
    expect(screen.getByText(/installazione fallita|installation failed/i)).toBeTruthy();
    expect(screen.getByText(/uscito con codice 1/)).toBeTruthy();
  });

  it("componente non auto-installabile: comando manuale sempre presente", () => {
    render(<ComponentRow c={comp({ auto_installable: false })} onChanged={() => {}} />);
    expect(screen.getByText(/pip install/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /installa|install/i })).toBeNull();
  });

  it("disabled dal genitore disattiva il bottone Installa (fix 2b)", () => {
    render(<ComponentRow c={comp({})} onChanged={() => {}} disabled />);
    const btn = screen.getByRole("button", { name: /installa|install/i }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("avvisa il genitore quando inizia e quando finisce un'installazione, senza un secondo polling", async () => {
    startInstall.mockResolvedValue({ key: "essentia", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "essentia", status: "done", log: [], detail: null });
    const onBusyChange = vi.fn();
    const onChanged = vi.fn();
    render(<ComponentRow c={comp({})} onChanged={onChanged} onBusyChange={onBusyChange} />);
    fireEvent.click(screen.getByRole("button", { name: /installa|install/i }));

    await waitFor(() => expect(onBusyChange).toHaveBeenCalledWith(true));
    // getInstallStatus è quel che ComponentRow già chiama a polling: nessuna
    // seconda fonte di verità va introdotta per sapere quando l'install finisce.
    await waitFor(() => expect(onBusyChange).toHaveBeenCalledWith(false), { timeout: 3000 });
    expect(onChanged).toHaveBeenCalled();
  });

  it("una riga che si smonta a metà installazione rilascia il lucchetto del genitore", async () => {
    startInstall.mockResolvedValue({ key: "essentia", status: "running", log: [], detail: null });
    // Il polling resta "running" per sempre: quel che conta è che lo
    // smontaggio, non un eventuale stato terminale, liberi il lucchetto.
    getInstallStatus.mockResolvedValue({ key: "essentia", status: "running", log: [], detail: null });
    const onBusyChange = vi.fn();
    const { unmount } = render(<ComponentRow c={comp({})} onChanged={() => {}} onBusyChange={onBusyChange} />);
    fireEvent.click(screen.getByRole("button", { name: /installa|install/i }));

    await waitFor(() => expect(onBusyChange).toHaveBeenCalledWith(true));
    onBusyChange.mockClear();

    unmount();

    expect(onBusyChange).toHaveBeenCalledWith(false);
  });
});

describe("ComponentRow: dove andare quando manca", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("mostra sempre il link alla documentazione del componente", () => {
    render(<ComponentRow c={comp({ present: true })} onChanged={() => {}} />);
    const link = screen.getByRole("link") as HTMLAnchorElement;
    expect(link.href).toContain("essentia.upf.edu");
  });

  it("componente senza ricetta: dice che non c'è un comando invece di tacere", () => {
    // slskd è un demone separato: senza questo, la riga diceva "non trovato"
    // e nient'altro — nessun comando, nessuna spiegazione, nessun link utile.
    render(<ComponentRow c={comp({
      key: "slskd", kind: "daemon", auto_installable: false,
      install_command: null, docs: "https://github.com/slskd/slskd/releases",
    })} onChanged={() => {}} />);
    expect(screen.getByText(/non c'è un comando|no single command/i)).toBeTruthy();
  });

  it("ricetta brew: avvisa che Homebrew non è preinstallato", () => {
    render(<ComponentRow c={comp({
      key: "ffmpeg", auto_installable: false,
      install_command: ["brew", "install", "ffmpeg"],
    })} onChanged={() => {}} />);
    expect(screen.getByText(/non include|does not come with/i)).toBeTruthy();
    const brew = screen.getAllByRole("link").find((a) => (a as HTMLAnchorElement).href.includes("brew.sh"));
    expect(brew).toBeTruthy();
  });

  it("ricetta non-brew: nessun avviso su Homebrew", () => {
    render(<ComponentRow c={comp({
      auto_installable: false, install_command: ["pip", "install", "essentia"],
    })} onChanged={() => {}} />);
    expect(screen.queryByText(/non include|does not come with/i)).toBeNull();
  });
});
