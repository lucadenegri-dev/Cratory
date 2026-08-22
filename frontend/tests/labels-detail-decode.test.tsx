import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

/* Cancello comportamentale, non solo testuale: tests/rotte-query-string.test.ts
   verifica che il sorgente non contenga piu' `decodeURIComponent` (pin della
   regressione esatta), ma non prova nulla sul comportamento a runtime. Qui si
   renderizza davvero la pagina con una label che contiene un `%` letterale
   (es. "Techno 100%"): e' il caso che romperebbe, perche' un secondo
   `decodeURIComponent` su un `%` non seguito da due cifre esadecimali solleva
   `URIError` e manda in crash la pagina. Uno spazio, invece, ripasserebbe
   indenne da una doppia decodifica: non e' un caso utile a questa prova. */

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams({ label: "Techno 100%" }),
}));

const mocks = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiGet: mocks.apiGet,
}));

const { default: LabelDetail } = await import("@/app/labels/detail/page");
const { PlayerProvider } = await import("@/lib/player");

describe("pagina di dettaglio label con un % letterale", () => {
  afterEach(cleanup);

  it("si renderizza senza sollevare URIError", async () => {
    mocks.apiGet.mockResolvedValue({ total: 0, items: [] });
    render(
      <PlayerProvider>
        <LabelDetail />
      </PlayerProvider>,
    );
    expect(await screen.findByText("Techno 100%")).toBeTruthy();
  });
});
