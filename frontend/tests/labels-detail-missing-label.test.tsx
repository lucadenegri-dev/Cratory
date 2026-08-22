import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

/* /labels/detail e' raggiungibile senza `?label=` da quando il dettaglio e'
   passato da segmento di percorso a query string (rotta statica): "label" e'
   allora "" (vedi il guard in app/labels/detail/page.tsx). apiGet scarta i
   query param vuoti (lib/api/client.ts), quindi senza guard la richiesta
   degrada silenziosamente a "/api/tracks" SENZA filtro: la pagina mostrerebbe
   l'intera libreria sotto un'intestazione vuota, come se ne fosse il
   contenuto di una label. Qui si simula esattamente quell'esito: apiGet
   risolve con una "libreria intera" fittizia riconoscibile, e la prova e' che
   quel contenuto non compare mai in pagina. */

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

const mocks = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiGet: mocks.apiGet,
}));

const { default: LabelDetail } = await import("@/app/labels/detail/page");
const { PlayerProvider } = await import("@/lib/player");

// "Libreria intera" fittizia: se il guard mancasse, apiGet la risolverebbe e
// questi titoli finirebbero nella tabella.
const wholeLibrary = {
  total: 2,
  items: [
    { id: 1, title: "Traccia Libreria Uno", artist: "Artista Uno", playlists: [], status: "imported" },
    { id: 2, title: "Traccia Libreria Due", artist: "Artista Due", playlists: [], status: "imported" },
  ],
};

describe("pagina di dettaglio label senza parametro `label`", () => {
  afterEach(cleanup);

  it("non renderizza l'intera libreria: niente fetch, alert di errore al suo posto", async () => {
    mocks.apiGet.mockResolvedValue(wholeLibrary);
    render(
      <PlayerProvider>
        <LabelDetail />
      </PlayerProvider>,
    );

    // Il guard decide a render, prima ancora che una promise possa risolvere:
    // l'alert e' gia' li'. Il testo e' spezzato in due nodi ("⚠ " + il
    // messaggio), quindi si legge il textContent del ruolo alert invece di
    // cercare la stringa esatta con getByText.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("⚠ Playlist non trovata");

    // La libreria intera non e' mai stata richiesta ne' mostrata.
    expect(mocks.apiGet).not.toHaveBeenCalled();
    expect(screen.queryByText("Traccia Libreria Uno")).toBeNull();
    expect(screen.queryByText("Traccia Libreria Due")).toBeNull();
  });
});
