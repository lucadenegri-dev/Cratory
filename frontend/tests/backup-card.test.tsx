import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getBackupEstimate: vi.fn(),
  createBackup: vi.fn(),
  prepareRestore: vi.fn(),
  confirmRestore: vi.fn(),
  cancelRestore: vi.fn(),
  lastRestore: vi.fn(),
  pickPath: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

const guscio = vi.hoisted(() => ({ nelGuscio: false, riavviaOra: vi.fn() }));
vi.mock("@/lib/updates", () => ({
  useAggiornamento: () => ({ ...guscio, stato: { fase: "sconosciuto" }, controllaOra: vi.fn(), installaOra: vi.fn() }),
}));

import { BackupCard } from "@/components/settings/backup-card";
import { ApiError } from "@/lib/api";

const stima = (extra = {}) => ({
  byte: 23_400_000,
  voci: [
    { nome: "database", byte: 20_000_000, presente: true, file: 1 },
    { nome: "covers", byte: 3_400_000, presente: true, file: 4 },
    { nome: "env", byte: 100, presente: true, file: 1 },
    { nome: "slskd", byte: 50, presente: true, file: 1 },
  ],
  last_backup_at: null as string | null,
  nome_di_default: "cratory-backup-20260913-1840.zip",
  picker_disponibile: true,
  ...extra,
});

beforeEach(() => {
  api.getBackupEstimate.mockResolvedValue(stima());
  api.lastRestore.mockResolvedValue(null);
  guscio.nelGuscio = false;
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
  guscio.riavviaOra.mockReset();
});

describe("scheda Dati", () => {
  it("dice che non c'è ancora un backup e quanto peserebbe", async () => {
    render(<BackupCard />);
    expect(await screen.findByText("Nessun backup finora")).toBeTruthy();
    expect(screen.getByText(/circa 23 MB · database, 4 cover, credenziali/)).toBeTruthy();
  });

  it("con una sola cover la stima dice «1 cover»", async () => {
    api.getBackupEstimate.mockResolvedValue(stima({
      voci: [
        { nome: "database", byte: 20_000_000, presente: true, file: 1 },
        { nome: "covers", byte: 12_000, presente: true, file: 1 },
        { nome: "env", byte: 100, presente: true, file: 1 },
        { nome: "slskd", byte: 50, presente: true, file: 1 },
      ],
    }));
    render(<BackupCard />);
    expect(await screen.findByText(/database, 1 cover, credenziali/)).toBeTruthy();
  });

  it("mostra la data dell'ultimo backup", async () => {
    api.getBackupEstimate.mockResolvedValue(stima({ last_backup_at: "2026-09-12T16:40:00+00:00" }));
    render(<BackupCard />);
    expect(await screen.findByText(/Ultimo backup: 12 set 2026/)).toBeTruthy();
  });

  it("senza picker il backup va al backend con path nullo e mostra dove è finito", async () => {
    api.getBackupEstimate.mockResolvedValue(stima({ picker_disponibile: false }));
    api.createBackup.mockResolvedValue({ percorso: "/Users/x/Downloads/b.zip", byte: 23_400_000, creato_il: "x" });
    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Crea backup…"));
    await waitFor(() => expect(api.createBackup).toHaveBeenCalledWith(null));
    expect(await screen.findByText(/Backup scritto in \/Users\/x\/Downloads\/b.zip \(23 MB\)/)).toBeTruthy();
    expect(api.pickPath).not.toHaveBeenCalled();
    // Senza picker il ripristino non si offre.
    expect(screen.queryByText("Ripristina da backup…")).toBeNull();
  });

  it("con il picker chiede dove salvare, col nome di default", async () => {
    api.pickPath.mockResolvedValue({ path: "/Users/x/Desktop/b.zip" });
    api.createBackup.mockResolvedValue({ percorso: "/Users/x/Desktop/b.zip", byte: 1_000_000, creato_il: "x" });
    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Crea backup…"));
    await waitFor(() => expect(api.pickPath).toHaveBeenCalledWith("save", undefined, "Salva il backup di Cratory", "cratory-backup-20260913-1840.zip"));
    await waitFor(() => expect(api.createBackup).toHaveBeenCalledWith("/Users/x/Desktop/b.zip"));
  });

  it("il ripristino mostra il riepilogo, e Annulla scarta lo staging", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({
      creato_il: "2026-09-01T10:00:00+00:00", app_version: "1.0.7", tracce: 3412, playlist: 58,
      membri: [], ha_credenziali: true,
    });
    api.cancelRestore.mockResolvedValue(undefined);
    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    expect(await screen.findByText(/3412 tracce, 58 playlist/)).toBeTruthy();
    expect(screen.getByText(/versione 1.0.7/)).toBeTruthy();
    expect(screen.getByText("Include le credenziali.")).toBeTruthy();
    expect(screen.getByText(/messi da parte/)).toBeTruthy();
    fireEvent.click(screen.getByText("Annulla"));
    await waitFor(() => expect(api.cancelRestore).toHaveBeenCalled());
    expect(api.confirmRestore).not.toHaveBeenCalled();
  });

  it("la conferma nel guscio riavvia; nel browser chiede di riavviare il backend", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({ creato_il: null, app_version: null, tracce: 0, playlist: 0, membri: [], ha_credenziali: false });
    api.confirmRestore.mockResolvedValue({ riavvio_necessario: true });

    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));
    expect(await screen.findByText(/Riavvia il backend per completarlo/)).toBeTruthy();
    expect(guscio.riavviaOra).not.toHaveBeenCalled();
    cleanup();

    guscio.nelGuscio = true;
    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));
    await waitFor(() => expect(guscio.riavviaOra).toHaveBeenCalled());
  });

  it("Annulla ed Escape sono inerti mentre la conferma è in corso", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({
      creato_il: "2026-09-01T10:00:00+00:00", app_version: "1.0.7", tracce: 3412, playlist: 58,
      membri: [], ha_credenziali: true,
    });
    // `confirmRestore` resta in sospeso finché non chiamiamo `release`: nella
    // finestra in cui è in volo, Annulla/Escape/backdrop non devono poter
    // annullare uno scambio che sul backend potrebbe già essere committato.
    let release: (v: { riavvio_necessario: boolean }) => void = () => {};
    api.confirmRestore.mockReturnValue(new Promise<{ riavvio_necessario: boolean }>((resolve) => { release = resolve; }));

    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));

    // Annulla è disabilitato mentre la conferma è in volo.
    await waitFor(() => expect(screen.getByText("Annulla")).toHaveProperty("disabled", true));
    fireEvent.click(screen.getByText("Annulla"));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(api.cancelRestore).not.toHaveBeenCalled();
    // Il modal resta aperto, col riepilogo ancora in vista.
    expect(screen.getByText(/3412 tracce, 58 playlist/)).toBeTruthy();

    release({ riavvio_necessario: true });
    expect(await screen.findByText(/Riavvia il backend per completarlo/)).toBeTruthy();
    expect(api.cancelRestore).not.toHaveBeenCalled();
  });

  it("chiudere il messaggio «riavvia il backend» non annulla il ripristino confermato", async () => {
    // Dopo `confirmRestore` il marker è scritto: Escape sul messaggio finale
    // deve solo chiudere il messaggio, non mandare la DELETE che cancella
    // marker e staging.
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({ creato_il: null, app_version: null, tracce: 0, playlist: 0, membri: [], ha_credenziali: false });
    api.confirmRestore.mockResolvedValue({ riavvio_necessario: true });
    api.cancelRestore.mockResolvedValue(undefined);

    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));
    expect(await screen.findByText(/Riavvia il backend per completarlo/)).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByText(/Riavvia il backend per completarlo/)).toBeNull());
    expect(api.cancelRestore).not.toHaveBeenCalled();
  });

  it("se il riavvio nel guscio fallisce, resta il messaggio di riavvio manuale", async () => {
    // `confirmRestore` è già andato a buon fine: il ripristino è scritto sul
    // backend e un riavvio fallito non lo annulla — va solo fatto a mano.
    guscio.nelGuscio = true;
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({ creato_il: null, app_version: null, tracce: 0, playlist: 0, membri: [], ha_credenziali: false });
    api.confirmRestore.mockResolvedValue({ riavvio_necessario: true });
    api.cancelRestore.mockResolvedValue(undefined);
    guscio.riavviaOra.mockRejectedValue(new Error("il guscio non risponde"));

    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));

    expect(await screen.findByText(/Riavvia il backend per completarlo/)).toBeTruthy();
    expect(api.cancelRestore).not.toHaveBeenCalled();
  });

  it("un job in corso diventa una frase che lo nomina", async () => {
    // Il client traduce il codice prima di sollevare: qui arriva già la frase.
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockRejectedValue(new ApiError(
      "C'è un lavoro in corso (analisi BPM/key): aspetta che finisca o fermalo, poi riprova.", 409, "job_in_corso",
    ));
    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Ripristina da backup…"));
    expect(await screen.findByText(/lavoro in corso \(analisi BPM\/key\)/)).toBeTruthy();
  });

  it("mostra l'esito dell'ultimo ripristino", async () => {
    api.lastRestore.mockResolvedValue({ stato: "ok", applicato_il: "2026-09-13T08:00:00+00:00", backup_creato_il: "2026-09-01T10:00:00+00:00", tracce: 1, playlist: 1 });
    render(<BackupCard />);
    expect(await screen.findByText(/Ripristinato il 13 set 2026 dal backup del 01 set 2026/)).toBeTruthy();
  });
});
