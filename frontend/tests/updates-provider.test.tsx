import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

// `vi.mock` viene issata sopra gli import: una `const finto` dichiarata qui
// sotto non esisterebbe ancora quando la fabbrica gira. `vi.hoisted` sale
// insieme alle mock ed è l'unico modo di condividere lo stato con loro.
const finto = vi.hoisted(() => ({
  nelGuscio: true,
  controlla: vi.fn(),
  installa: vi.fn(),
  riavvia: vi.fn(),
}));

vi.mock("@/lib/external-url", () => ({ isDesktopShell: () => finto.nelGuscio }));
vi.mock("@/lib/updates-bridge", async () => {
  const vero = await vi.importActual<typeof import("@/lib/updates-bridge")>("@/lib/updates-bridge");
  return {
    erroreDi: vero.erroreDi,
    controlla: () => finto.controlla(),
    installa: () => finto.installa(),
    riavvia: () => finto.riavvia(),
    ascoltaProgresso: () => Promise.resolve(() => {}),
    ascoltaInstallazione: () => Promise.resolve(() => {}),
  };
});

import { AggiornamentoProvider, useAggiornamento } from "@/lib/updates";

function Sonda() {
  const { stato } = useAggiornamento();
  return <span data-testid="fase">{stato.fase}</span>;
}

const monta = () =>
  render(
    <AggiornamentoProvider>
      <Sonda />
    </AggiornamentoProvider>,
  );

beforeEach(() => {
  finto.nelGuscio = true;
  finto.controlla = vi.fn().mockResolvedValue(null);
  finto.installa = vi.fn().mockResolvedValue(undefined);
  finto.riavvia = vi.fn().mockResolvedValue(undefined);
});
afterEach(cleanup);

describe("provider degli aggiornamenti", () => {
  it("fuori dal guscio non chiede niente a nessuno", async () => {
    finto.nelGuscio = false;
    monta();
    await waitFor(() => expect(screen.getByTestId("fase").textContent).toBe("sconosciuto"));
    expect(finto.controlla).not.toHaveBeenCalled();
  });

  it("all'avvio, nel guscio, controlla una volta sola", async () => {
    monta();
    await waitFor(() => expect(screen.getByTestId("fase").textContent).toBe("aggiornato"));
    expect(finto.controlla).toHaveBeenCalledTimes(1);
  });

  it("una versione nuova diventa 'disponibile'", async () => {
    finto.controlla = vi.fn().mockResolvedValue({ versione: "1.0.4", note: "note", data: null });
    monta();
    await waitFor(() => expect(screen.getByTestId("fase").textContent).toBe("disponibile"));
  });

  it("un controllo fallito non diventa mai 'aggiornato'", async () => {
    finto.controlla = vi.fn().mockRejectedValue({ codice: "controllo", dettaglio: "404" });
    monta();
    await waitFor(() => expect(screen.getByTestId("fase").textContent).toBe("non_verificabile"));
  });
});
