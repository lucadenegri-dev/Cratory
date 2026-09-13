import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getBackupEstimate: vi.fn(),
  createBackup: vi.fn(),
  pickPath: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

import { ConfermaAggiornamento } from "@/components/settings/conferma-aggiornamento";

const stima = (picker = true) => ({
  byte: 23_400_000, voci: [], last_backup_at: null, nome_di_default: "b.zip", picker_disponibile: picker,
});

beforeEach(() => {
  api.getBackupEstimate.mockResolvedValue(stima());
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
});

const monta = () => {
  const onInstall = vi.fn();
  const onClose = vi.fn();
  render(<ConfermaAggiornamento open onClose={onClose} onInstall={onInstall} />);
  return { onInstall, onClose };
};

describe("la conferma dell'aggiornamento", () => {
  it("con la stima offre tre uscite e dice i MB", async () => {
    monta();
    expect(await screen.findByText(/Occuperebbe circa 23 MB/)).toBeTruthy();
    expect(screen.getByText("Backup e aggiorna")).toBeTruthy();
    expect(screen.getByText("Aggiorna senza backup")).toBeTruthy();
    expect(screen.getByText("Annulla")).toBeTruthy();
    expect(screen.getByText(/viene interrotto/)).toBeTruthy();
  });

  it("senza stima restano le due uscite di prima", async () => {
    api.getBackupEstimate.mockRejectedValue(new Error("giù"));
    monta();
    expect(await screen.findByText("Scarica e installa (≈172 MB)")).toBeTruthy();
    expect(screen.queryByText("Backup e aggiorna")).toBeNull();
    expect(screen.queryByText(/Occuperebbe/)).toBeNull();
  });

  it("aggiorna senza backup installa e basta", async () => {
    const { onInstall } = monta();
    fireEvent.click(await screen.findByText("Aggiorna senza backup"));
    expect(onInstall).toHaveBeenCalled();
    expect(api.createBackup).not.toHaveBeenCalled();
  });

  it("il dialogo annullato riporta alla modale senza installare", async () => {
    api.pickPath.mockResolvedValue({ path: null });
    const { onInstall, onClose } = monta();
    fireEvent.click(await screen.findByText("Backup e aggiorna"));
    // L'annullamento del picker è asincrono: si attende che la modale si stabilizzi di nuovo.
    expect(await screen.findByText("Backup e aggiorna")).toBeTruthy();
    expect(api.createBackup).not.toHaveBeenCalled();
    expect(onInstall).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("un backup fallito mostra l'errore e non installa", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.createBackup.mockRejectedValue(new Error("disco pieno"));
    const { onInstall } = monta();
    fireEvent.click(await screen.findByText("Backup e aggiorna"));
    expect(await screen.findByText(/Il backup non è riuscito/)).toBeTruthy();
    expect(screen.getByText("disco pieno")).toBeTruthy();
    expect(onInstall).not.toHaveBeenCalled();
  });

  it("percorso felice: backup, poi installazione", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.createBackup.mockResolvedValue({ percorso: "/x/b.zip", byte: 1, creato_il: "x" });
    const { onInstall } = monta();
    fireEvent.click(await screen.findByText("Backup e aggiorna"));
    await waitFor(() => expect(onInstall).toHaveBeenCalled());
    expect(api.pickPath).toHaveBeenCalledWith("save", undefined, "Salva il backup di Cratory", "b.zip");
    expect(api.createBackup).toHaveBeenCalledWith("/x/b.zip");
  });

  it("senza picker il backup va in Downloads, senza dialogo", async () => {
    api.getBackupEstimate.mockResolvedValue(stima(false));
    api.createBackup.mockResolvedValue({ percorso: "/Users/x/Downloads/b.zip", byte: 1, creato_il: "x" });
    const { onInstall } = monta();
    fireEvent.click(await screen.findByText("Backup e aggiorna"));
    await waitFor(() => expect(onInstall).toHaveBeenCalled());
    expect(api.pickPath).not.toHaveBeenCalled();
    expect(api.createBackup).toHaveBeenCalledWith(null);
  });
});
