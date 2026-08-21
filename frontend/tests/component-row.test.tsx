import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ComponentRow } from "@/components/setup/component-row";
import type { ProbeComponent } from "@/lib/api";

// Il mock deve esporre OGNI export usato dal componente: vitest solleva
// "No 'X' export is defined on the mock" al primo accesso mancante
// (stesso pattern di tests/credential-field.test.tsx). daemonConfig/daemonStart
// sono arrivati col demone gestito qui dentro (ex passo dedicato del wizard).
const startInstall = vi.fn();
const getInstallStatus = vi.fn();
const daemonConfig = vi.fn();
const daemonStart = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  startInstall: (...a: unknown[]) => startInstall(...a),
  getInstallStatus: (...a: unknown[]) => getInstallStatus(...a),
  daemonConfig: (...a: unknown[]) => daemonConfig(...a),
  daemonStart: (...a: unknown[]) => daemonStart(...a),
}));

function comp(over: Partial<ProbeComponent>): ProbeComponent {
  return {
    key: "essentia",
    kind: "system",
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
    // Nel backend auto_installable e installable sono ormai lo stesso valore
    // (dipendono solo dall'esistere una build per la piattaforma): un
    // componente "non auto-installabile" è anche "non installable".
    render(<ComponentRow c={comp({ auto_installable: false, installable: false })} onChanged={() => {}} />);
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

  it("componente di sistema senza ricetta: dice che non c'è un comando invece di tacere", () => {
    // slskd (kind "daemon") ha il suo blocco dedicato più sotto e non passa
    // mai da qui: questo copre un componente di sistema che semplicemente non
    // ha una ricetta per la piattaforma corrente.
    render(<ComponentRow c={comp({
      key: "finto", auto_installable: false, installable: false, install_command: null,
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

describe("ComponentRow: installabilità", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("senza build per la piattaforma non offre il bottone", () => {
    render(<ComponentRow c={comp({
      key: "ffmpeg", installable: false, auto_installable: false,
      install_command: ["brew", "install", "ffmpeg"],
    })} onChanged={() => {}} />);
    expect(screen.queryByRole("button", { name: /installa|install/i })).toBeNull();
    expect(screen.getByText(/brew install ffmpeg/)).toBeTruthy();
  });
});

// Il demone (slskd) non ha più un passo dedicato: la sua riga qui gestisce
// per intero sia il caso "risponde già" (frase condivisa, niente form) sia
// il caso "non risponde" (credenziali Soulseek + un'unica azione che scarica,
// configura e avvia) — carry-over dal vecchio steps/slskd.tsx, incluso
// l'ordine (configura prima di scaricare) e il controllo sull'errore di
// installazione prima di avviare.
function daemon(over: Partial<ProbeComponent> = {}): ProbeComponent {
  return comp({
    key: "slskd", kind: "daemon", installable: true, auto_installable: true,
    install_command: null, docs: "https://github.com/slskd/slskd/releases",
    ...over,
  });
}

describe("ComponentRow: demone slskd", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("demone già raggiungibile: solo la frase condivisa, nessun modulo credenziali", () => {
    render(<ComponentRow c={daemon({ present: true })} onChanged={() => {}} />);
    expect(screen.getByText(/impostazioni|settings page/i)).toBeTruthy();
    expect(screen.queryByLabelText(/username/i)).toBeNull();
    expect(screen.queryByLabelText(/password/i)).toBeNull();
  });

  it("demone non raggiungibile: chiede le credenziali e installa (fix)", async () => {
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    startInstall.mockResolvedValue({ key: "slskd", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "slskd", status: "done", log: [], detail: null });
    daemonStart.mockResolvedValue({ reachable: true, owned: true, pid: 7 });
    const onChanged = vi.fn();
    render(<ComponentRow c={daemon({ present: false })} onChanged={onChanged} />);

    // Niente bottone finché mancano username e password.
    const bottone = screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }) as HTMLButtonElement;
    expect(bottone.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "segreta" } });
    expect(bottone.disabled).toBe(false);
    fireEvent.click(bottone);

    await waitFor(() => expect(daemonConfig).toHaveBeenCalledWith({ username: "io", password: "segreta" }));
    await waitFor(() => expect(startInstall).toHaveBeenCalledWith("slskd"));
    await waitFor(() => expect(daemonStart).toHaveBeenCalled());
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("la password non resta nel campo dopo il salvataggio", async () => {
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    startInstall.mockResolvedValue({ key: "slskd", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "slskd", status: "done", log: [], detail: null });
    daemonStart.mockResolvedValue({ reachable: true, owned: true, pid: 7 });
    render(<ComponentRow c={daemon({ present: false })} onChanged={() => {}} />);

    const pwd = screen.getByLabelText(/password/i) as HTMLInputElement;
    fireEvent.change(pwd, { target: { value: "segreta" } });
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.click(screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }));

    await waitFor(() => expect(daemonConfig).toHaveBeenCalled());
    await waitFor(() => expect(pwd.value).toBe(""));
  });

  it("installazione fallita non avvia il demone e mostra l'errore", async () => {
    // Stesso fix del vecchio passo dedicato: un job che finisce in "error"
    // non deve far scattare daemonStart() — né "slskd non è installato" né,
    // peggio, l'avvio silenzioso di una copia vecchia già presente.
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    startInstall.mockResolvedValue({ key: "slskd", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "slskd", status: "error", log: [], detail: "checksum errato" });
    render(<ComponentRow c={daemon({ present: false })} onChanged={() => {}} />);

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "segreta" } });
    fireEvent.click(screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }));

    await waitFor(() => expect(daemonConfig).toHaveBeenCalled());
    expect(await screen.findByText(/checksum errato/i)).toBeTruthy();
    expect(daemonStart).not.toHaveBeenCalled();
  });

  it("il bottone del demone rispetta il disabled del genitore", () => {
    render(<ComponentRow c={daemon({ present: false })} onChanged={() => {}} disabled />);
    const bottone = screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }) as HTMLButtonElement;
    expect(bottone.disabled).toBe(true);
  });

  it("avvisa il genitore quando l'installazione del demone inizia e finisce (stesso lucchetto delle altre righe)", async () => {
    // startInstall condivide un solo job col backend (409 altrimenti): questa
    // riga deve annunciare busy come tutte le altre, non solo quelle di
    // ffmpeg/fpcalc.
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    startInstall.mockResolvedValue({ key: "slskd", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "slskd", status: "done", log: [], detail: null });
    daemonStart.mockResolvedValue({ reachable: true, owned: true, pid: 7 });
    const onBusyChange = vi.fn();
    render(<ComponentRow c={daemon({ present: false })} onChanged={() => {}} onBusyChange={onBusyChange} />);

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "segreta" } });
    fireEvent.click(screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }));

    await waitFor(() => expect(onBusyChange).toHaveBeenCalledWith(true));
    await waitFor(() => expect(onBusyChange).toHaveBeenCalledWith(false));
  });
});
