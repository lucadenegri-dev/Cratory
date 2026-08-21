import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SlskdStep } from "@/components/setup/steps/slskd";

const daemonStatus = vi.fn();
const daemonStart = vi.fn();
const daemonStop = vi.fn();
const daemonConfig = vi.fn();
// Il mock deve esporre OGNI export usato dal componente (e da PathField/
// CredentialField, che passano dallo stesso barrel "@/lib/api"): vitest
// solleva al primo accesso mancante.
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getConfigSettings: vi.fn().mockResolvedValue({
    slskd_url: { value: "http://localhost:5030", source: "env", detail: null },
    slskd_download_dir: { value: "/tmp/dl", source: "env", detail: null },
    secrets: { slskd_api_key: { configured: false, source: "env", hint: null } },
  }),
  patchConfigSettings: vi.fn(),
  pickerAvailability: vi.fn().mockResolvedValue({ available: false }),
  pickPath: vi.fn(),
  slskdStatus: vi.fn().mockResolvedValue({ configured: true, reachable: false }),
  daemonStatus: (...a: unknown[]) => daemonStatus(...a),
  daemonStart: (...a: unknown[]) => daemonStart(...a),
  daemonStop: (...a: unknown[]) => daemonStop(...a),
  daemonConfig: (...a: unknown[]) => daemonConfig(...a),
  startInstall: vi.fn().mockResolvedValue({ status: "running" }),
  getInstallStatus: vi.fn().mockResolvedValue({ status: "done" }),
}));

describe("SlskdStep", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("demone acceso da altri: nessun bottone Ferma", async () => {
    // Non spegniamo un processo che non abbiamo avviato noi: il bottone non
    // deve nemmeno comparire.
    daemonStatus.mockResolvedValue({ reachable: true, owned: false, pid: null });
    render(<SlskdStep />);
    await waitFor(() => expect(daemonStatus).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /ferma|stop/i })).toBeNull();
  });

  it("demone avviato da noi: il bottone Ferma c'è", async () => {
    daemonStatus.mockResolvedValue({ reachable: true, owned: true, pid: 42 });
    render(<SlskdStep />);
    expect(await screen.findByRole("button", { name: /ferma|stop/i })).toBeTruthy();
  });

  it("proprietà del demone non rilevabile: nessun bottone Ferma e nessun 'avviato fuori'", async () => {
    // owned=null (es. Windows, dove i tool di processo non ci sono): non è
    // "non nostro", è "non lo sappiamo". L'utente non può fare nulla in
    // nessuno dei due casi, ma dirgli la cosa sbagliata è peggio che non
    // dirgli niente.
    daemonStatus.mockResolvedValue({ reachable: true, owned: null, pid: null });
    render(<SlskdStep />);
    await waitFor(() => expect(daemonStatus).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /ferma|stop/i })).toBeNull();
    expect(screen.queryByText(/avviato fuori|elsewhere/i)).toBeNull();
    // Un messaggio sbagliato qualunque farebbe passare le due asserzioni sopra:
    // serve anche verificare che compaia proprio quello giusto.
    expect(await screen.findByText(/non è possibile stabilire|can't tell/i)).toBeTruthy();
  });

  it("il bottone Ferma si disabilita durante la chiamata e mostra l'errore se il demone rifiuta lo stop", async () => {
    // Prima di questo fix il click chiamava setDaemon(await daemonStop())
    // senza try/catch né stato di occupato: un rigetto (race sulla
    // proprietà, rete giù) spariva inosservato e il bottone restava
    // cliccabile all'infinito.
    daemonStatus.mockResolvedValue({ reachable: true, owned: true, pid: 42 });
    let rifiuta!: (e: Error) => void;
    daemonStop.mockReturnValue(new Promise((_, reject) => { rifiuta = reject; }));
    render(<SlskdStep />);
    const ferma = await screen.findByRole("button", { name: /ferma|stop/i }) as HTMLButtonElement;
    fireEvent.click(ferma);
    await waitFor(() => expect(ferma.disabled).toBe(true));
    rifiuta(new Error("non è più nostro"));
    await waitFor(() => expect(ferma.disabled).toBe(false));
    expect(await screen.findByText(/non è più nostro/i)).toBeTruthy();
  });

  it("la password non resta nel campo dopo il salvataggio", async () => {
    daemonStatus.mockResolvedValue({ reachable: false, owned: false, pid: null });
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    // Il demone resta non raggiungibile anche dopo il tentativo di avvio: il
    // form (e quindi il campo password) resta montato, così verifichiamo lo
    // svuotamento del campo senza la variabile in più dello smontaggio del
    // form, che altrimenti lo sostituirebbe con la vista "in esecuzione".
    daemonStart.mockResolvedValue({ reachable: false, owned: false, pid: null });
    render(<SlskdStep />);
    const pwd = await screen.findByLabelText(/password/i) as HTMLInputElement;
    fireEvent.change(pwd, { target: { value: "segretissima" } });
    fireEvent.change(await screen.findByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.click(screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }));
    await waitFor(() => expect(daemonConfig).toHaveBeenCalled());
    await waitFor(() => expect(pwd.value).toBe(""));
  });

  it("omette porta e cartella download dalla configurazione: l'assente resta assente", async () => {
    // daemonConfig({username, password}) non deve riempire port/download_dir
    // "per aiutare": il backend legge l'assenza come "non toccare il valore
    // dell'utente". Un tempo li riempivamo e un utente si è visto sovrascrivere
    // una porta personalizzata.
    daemonStatus.mockResolvedValue({ reachable: false, owned: false, pid: null });
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    daemonStart.mockResolvedValue({ reachable: true, owned: true, pid: 7 });
    render(<SlskdStep />);
    fireEvent.change(await screen.findByLabelText(/password/i), { target: { value: "segretissima" } });
    fireEvent.change(await screen.findByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.click(screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }));
    await waitFor(() => expect(daemonConfig).toHaveBeenCalled());
    const call = daemonConfig.mock.calls[0][0];
    expect(call).toEqual({ username: "io", password: "segretissima" });
    expect(call.port).toBeUndefined();
    expect(call.download_dir).toBeUndefined();
  });
});
