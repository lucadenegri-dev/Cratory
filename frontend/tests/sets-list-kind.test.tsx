import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const listApi = vi.hoisted(() => ({ apiGet: vi.fn(), createManualSet: vi.fn(), apiDelete: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...listApi,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/sets",
  useSearchParams: () => new URLSearchParams(""),
}));

import SetsPage from "@/app/sets/page";

afterEach(() => {
  cleanup();
  Object.values(listApi).forEach((f) => f.mockReset());
  push.mockReset();
});

const dueSet = [
  { id: 1, name: "A mano", kind: "manual", strategy: null, target_duration_minutes: null, track_count: 0, total_duration_seconds: 0, generated_by: "manual", created_at: "2026-09-17T10:00:00" },
  { id: 2, name: "Generato", kind: "generated", strategy: "smooth", target_duration_minutes: 60, track_count: 12, total_duration_seconds: 3600, generated_by: "algorithmic", created_at: "2026-09-17T10:00:00" },
];

describe("lista dei set", () => {
  it("apre i set a mano sulla loro pagina", async () => {
    listApi.apiGet.mockResolvedValue(dueSet);
    render(<SetsPage />);
    const manual = (await screen.findByText("A mano")).closest("a");
    expect(manual?.getAttribute("href")).toBe("/sets/manual?id=1");
  });

  it("un set generato non si apre più: si può solo cancellare", async () => {
    // Deciso il 2026-09-19 con l'utente: la pagina di dettaglio classica non
    // esiste piu'. Meglio una riga che dice la verita' di un clic che porta
    // a una pagina che non c'e'.
    listApi.apiGet.mockResolvedValue(dueSet);
    render(<SetsPage />);
    await screen.findByText("Generato");
    expect(screen.getByText("Generato").closest("a")).toBeNull();
    expect(screen.getByText(/vecchio formato/i)).toBeTruthy();
    expect(screen.getByTitle(/Elimina/i)).toBeTruthy();
  });

  it("«Prepara un set» apre una bozza senza salvare niente", async () => {
    // Dal 2026-09-19 il set nasce alla prima traccia, non aprendo la pagina:
    // qui non deve partire nessuna creazione.
    listApi.apiGet.mockResolvedValue([]);
    render(<SetsPage />);
    fireEvent.click(await screen.findByText("Prepara un set"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/sets/manual"));
    expect(listApi.createManualSet).not.toHaveBeenCalled();
  });

  it("eliminare un set vecchio lo toglie dalla lista", async () => {
    listApi.apiGet.mockResolvedValue(dueSet);
    listApi.apiDelete.mockResolvedValue(undefined);
    render(<SetsPage />);
    await screen.findByText("Generato");
    fireEvent.click(screen.getByTitle(/Elimina/i));
    await waitFor(() => expect(listApi.apiDelete).toHaveBeenCalledWith("/api/sets/2"));
    await waitFor(() => expect(screen.queryByText("Generato")).toBeNull());
    // Quello a mano resta dov'e'.
    expect(screen.getByText("A mano")).toBeTruthy();
  });
});
