import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";

/* L'ordinamento con cui la libreria si APRE. Il default del backend è
   alfabetico per artista, che per una libreria che cresce è l'ordine meno
   utile: quello che si vuole vedere entrando è la roba appena arrivata. */

// La pagina ricorda la vista (griglia/lista) in localStorage, che in questo
// ambiente di test non c'è: uno stub minimo, così il montaggio arriva in fondo.
// Non è il soggetto del test, è solo l'impalcatura per raggiungerlo.
const memoria = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => memoria.get(k) ?? null,
  setItem: (k: string, v: string) => void memoria.set(k, v),
  removeItem: (k: string) => void memoria.delete(k),
  clear: () => memoria.clear(),
});

let query = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/library",
  useSearchParams: () => query,
}));

const apiGet = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiGet: (...a: unknown[]) => apiGet(...a),
}));

const { default: LibraryPage } = await import("@/app/library/page");
const { PlayerProvider } = await import("@/lib/player");

afterEach(cleanup);

/** I parametri della PRIMA chiamata a /api/tracks: l'ordinamento d'apertura. */
async function parametriDApertura(search: string): Promise<Record<string, unknown>> {
  // Senza questo, `find` sotto pesca la chiamata del test PRECEDENTE (i mock
  // accumulano fra i test) e si finisce per misurare l'apertura sbagliata.
  apiGet.mockClear();
  apiGet.mockResolvedValue({ total: 0, items: [] });
  query = new URLSearchParams(search);
  render(<PlayerProvider><LibraryPage /></PlayerProvider>);
  await waitFor(() => {
    const call = apiGet.mock.calls.find((c) => c[0] === "/api/tracks");
    expect(call).toBeTruthy();
  });
  const call = apiGet.mock.calls.find((c) => c[0] === "/api/tracks")!;
  return call[1] as Record<string, unknown>;
}

describe("ordinamento d'apertura della libreria", () => {
  it("si apre sulle tracce aggiunte di recente, non in ordine alfabetico", async () => {
    const p = await parametriDApertura("");
    expect(p.sort).toBe("added_at");
    expect(p.order).toBe("desc");
  });

  it("un ordinamento scelto nell'URL vince sul default", async () => {
    // È così che tornando dal dettaglio di una traccia si ritrova la vista che
    // si era lasciata: il link indietro riporta i propri parametri.
    const p = await parametriDApertura("sort=bpm&order=asc");
    expect(p.sort).toBe("bpm");
    expect(p.order).toBe("asc");
  });

  it("i filtri nell'URL non trascinano con sé l'ordinamento", async () => {
    // Un URL con filtri ma senza `sort` è comunque un'apertura: il default vale.
    const p = await parametriDApertura("genre=Techno");
    expect(p.genre).toBe("Techno");
    expect(p.sort).toBe("added_at");
    expect(p.order).toBe("desc");
  });
});
