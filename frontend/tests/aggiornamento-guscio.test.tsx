import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { StatoAggiornamento } from "@/lib/updates";

// `vi.hoisted`: la fabbrica di `vi.mock` gira prima delle dichiarazioni del
// modulo, quindi lo stato condiviso deve salire insieme a lei.
const finto = vi.hoisted(() => ({
  stato: { fase: "sconosciuto" } as StatoAggiornamento,
  controllaOra: vi.fn(),
  installaOra: vi.fn(),
  riavviaOra: vi.fn(),
}));

vi.mock("@/lib/updates", () => ({
  useAggiornamento: () => ({ ...finto, nelGuscio: true }),
}));

import { AggiornamentoGuscio } from "@/components/settings/aggiornamento-guscio";

afterEach(cleanup);

const monta = () => render(<AggiornamentoGuscio versione="Stai usando la 1.0.3" />);

describe("scheda aggiornamento nel guscio", () => {
  it("con una versione nuova offre l'installazione, e il clic chiede conferma prima", () => {
    finto.stato = { fase: "disponibile", info: { versione: "1.0.4", note: "note vere", data: null } };
    monta();
    expect(screen.getByText("note vere")).toBeTruthy();
    fireEvent.click(screen.getByText(/Scarica e installa/));
    // La conferma dice le tre cose vere; l'installazione non è ancora partita.
    expect(screen.getByText(/viene interrotto/)).toBeTruthy();
    expect(finto.installaOra).not.toHaveBeenCalled();
  });

  it("mostra i MB durante il download, e non lascia ripremere il controllo", () => {
    finto.stato = {
      fase: "scaricando",
      info: { versione: "1.0.4", note: null, data: null },
      scaricati: 90_000_000,
      totale: 180_000_000,
    };
    monta();
    expect(screen.getByText("Scaricati 90 MB di 180 MB")).toBeTruthy();
    expect(screen.getByText("Controlla aggiornamenti").closest("button")?.disabled).toBe(true);
  });

  it("dopo un fallimento offre il riavvio, perché il backend è già stato terminato", () => {
    finto.stato = {
      fase: "fallito",
      info: { versione: "1.0.4", note: null, data: null },
      errore: { codice: "installazione", dettaglio: "read-only file system" },
    };
    monta();
    expect(screen.getByText(/L'installazione non è riuscita/)).toBeTruthy();
    expect(screen.getByText("read-only file system")).toBeTruthy();
    fireEvent.click(screen.getByText("Riavvia l'app"));
    expect(finto.riavviaOra).toHaveBeenCalled();
  });

  it("un controllo fallito non dice che sei aggiornato", () => {
    finto.stato = { fase: "non_verificabile", errore: { codice: "controllo", dettaglio: "404" } };
    monta();
    expect(screen.getByText(/Non è stato possibile controllare/)).toBeTruthy();
    expect(screen.queryByText(/all'ultima versione/)).toBeNull();
  });

  it("mostra sempre la versione in uso, in ogni fase", () => {
    finto.stato = { fase: "installando", info: { versione: "1.0.4", note: null, data: null } };
    monta();
    expect(screen.getByText("Stai usando la 1.0.3")).toBeTruthy();
  });
});
