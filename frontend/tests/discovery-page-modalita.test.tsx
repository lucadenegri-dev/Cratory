import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { it as dict } from "@/lib/i18n/it";
import { similarHref } from "@/lib/discovery-dig";
import type { DiscoveryDigResponse, DiscoverySimilarResponse } from "@/lib/api/types";

/* Le due modalità della pagina Discovery (scavo e simili) leggono la STESSA
   query string e vivono nello stesso componente montato: passare dall'una
   all'altra non rimonta niente. Questi test coprono proprio quel confine, che
   i test dei singoli componenti non possono vedere. */

const push = vi.fn();
// La verità delle due modalità sta qui: i test la riscrivono e rifanno il
// render, esattamente come fa una navigazione client (o un back).
let query = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/discovery",
  useSearchParams: () => query,
}));

const discoveryDig = vi.fn();
const discoverySimilar = vi.fn();
const apiGet = vi.fn();
// Il resto di `@/lib/api` passa dall'originale: la pagina (e i componenti che
// monta) ne usa molto più di queste tre, e un mock a elenco chiuso cadrebbe al
// primo export non previsto.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  discoveryDig: (...a: unknown[]) => discoveryDig(...a),
  discoverySimilar: (...a: unknown[]) => discoverySimilar(...a),
  apiGet: (...a: unknown[]) => apiGet(...a),
  getDiscoveryGenres: () => Promise.resolve({ library: [], styles: [] }),
  getLabels: () => Promise.resolve([]),
}));

const { default: DiscoveryPage } = await import("@/app/discovery/page");

const DIG: DiscoveryDigResponse = {
  seed_type: "label", value: "Warp Records", source: "discogs", leads: [],
  pile_total: 5000, pile_reach: 500, seed_resolution: "label",
};

const SIM: DiscoverySimilarResponse = {
  track_id: 5, source: "bandcamp",
  origin: {
    artist: "Jasmín", title: "Bite The Hand That Feeds You", label: "Hessle Audio",
    year: 2025, tag: "bass", source_url: null, resolution: "release",
  },
  edges: {
    same_artist: { count: 2, absent_reason: null },
    same_label: { count: 3, absent_reason: null },
    same_period_style: { count: null, absent_reason: "off" },
  },
  leads: [],
};

const TRACK = { id: 5, artist: "Jasmín", title: "Bite The Hand" } as never;

// Il testo atteso viene dal dizionario, non ricopiato a mano: un cambio di
// stringa non deve far passare il test per il motivo sbagliato.
const AVVISO_PILA = dict.discovery.broadSeedLabel(
  (5000).toLocaleString("it"), (500).toLocaleString("it"), dict.discovery.sourceDiscogs);
const INTERRUTTORE = /Stile e periodo/;

afterEach(cleanup);

describe("pagina Discovery, confine fra scavo e simili", () => {
  it("l'avviso sulla pila non sopravvive al passaggio ai simili", async () => {
    discoveryDig.mockResolvedValue(DIG);
    query = new URLSearchParams("seed=label&value=Warp Records&depth=0&source=discogs");
    const view = render(<DiscoveryPage />);
    await waitFor(() => expect(screen.getByText(AVVISO_PILA)).toBeTruthy());

    // Stesso componente montato, altra query string: `dig` resta in memoria.
    discoverySimilar.mockResolvedValue(SIM);
    apiGet.mockResolvedValue(TRACK);
    query = new URLSearchParams("similar=5");
    view.rerender(<DiscoveryPage />);

    await waitFor(() => expect(screen.getByLabelText(INTERRUTTORE)).toBeTruthy());
    // «5.000 di 500 su Discogs» descriverebbe una pila che questa vista non ha.
    expect(screen.queryByText(AVVISO_PILA)).toBeNull();
  });

  it("l'interruttore stile/periodo non si smonta da sotto il cursore", async () => {
    let sblocca: (v: DiscoverySimilarResponse) => void = () => {};
    discoverySimilar
      .mockResolvedValueOnce(SIM)
      .mockImplementationOnce(() => new Promise((res) => { sblocca = res; }));
    apiGet.mockResolvedValue(TRACK);
    query = new URLSearchParams("similar=5");
    const view = render(<DiscoveryPage />);
    await waitFor(() => expect(screen.getByLabelText(INTERRUTTORE)).toBeTruthy());

    // Stessa traccia, altra domanda: il secondo giro è ancora in volo.
    query = new URLSearchParams("similar=5&style_period=1");
    view.rerender(<DiscoveryPage />);

    const box = screen.getByLabelText(INTERRUTTORE) as HTMLInputElement;
    expect(box.disabled).toBe(true);        // `busy` arriva davvero all'intestazione
    expect(screen.queryAllByRole("status")).toHaveLength(0); // niente spinner a pagina intera

    sblocca(SIM);
    await waitFor(() =>
      expect((screen.getByLabelText(INTERRUTTORE) as HTMLInputElement).disabled).toBe(false));
  });

  it("l'interruttore scrive style_period nell'URL, non solo nello stato locale", async () => {
    // Lo stato dei simili vive nella query string: senza il push, un ricarico o un
    // back tornerebbe a leggere l'interruttore spento mentre la vista lo mostra acceso.
    discoverySimilar.mockResolvedValue(SIM);
    apiGet.mockResolvedValue(TRACK);
    query = new URLSearchParams("similar=5");
    push.mockClear();
    render(<DiscoveryPage />);
    await waitFor(() => expect(screen.getByLabelText(INTERRUTTORE)).toBeTruthy());

    fireEvent.click(screen.getByLabelText(INTERRUTTORE));

    expect(push).toHaveBeenCalledWith(similarHref(5, true), { scroll: false });
  });

  it("un'altra traccia invece azzera il risultato e mostra lo spinner", async () => {
    discoverySimilar
      .mockResolvedValueOnce(SIM)
      .mockImplementationOnce(() => new Promise(() => {}));
    apiGet.mockResolvedValue(TRACK);
    query = new URLSearchParams("similar=5");
    const view = render(<DiscoveryPage />);
    await waitFor(() => expect(screen.getByLabelText(INTERRUTTORE)).toBeTruthy());

    query = new URLSearchParams("similar=9");
    view.rerender(<DiscoveryPage />);

    // Soggetto diverso: tenere l'intestazione di prima sarebbe mentire.
    expect(screen.queryByLabelText(INTERRUTTORE)).toBeNull();
    // `Loading` annida due role="status" (anche l'equalizzatore ne ha uno):
    // basta che l'etichetta dello spinner ci sia.
    expect(screen.getAllByRole("status").some(
      (n) => n.textContent?.includes(dict.discovery.similarInProgress))).toBe(true);
  });
});

/* La catena indietro: libreria -> traccia -> simili -> traccia -> libreria.
   Il valore che la tiene insieme è `from`, e il punto in cui si spezzava era
   proprio questo: i simili non lo trasportavano, così la traccia ritrovata
   non ricordava più i filtri da cui eri partito. */
describe("pagina Discovery, il link indietro dei simili", () => {
  const ORIGINE = "/library?genre=Techno&sort=bpm&order=desc";

  const linkIndietro = () =>
    (screen.getByText(dict.discovery.similarBackToTrack).closest("a") as HTMLAnchorElement);

  async function rendiConOrigine(from: string | null) {
    discoverySimilar.mockResolvedValue(SIM);
    apiGet.mockResolvedValue(TRACK);
    const p = new URLSearchParams("similar=5");
    if (from !== null) p.set("from", from);
    query = p;
    render(<DiscoveryPage />);
    await waitFor(() => expect(screen.getByLabelText(INTERRUTTORE)).toBeTruthy());
  }

  it("restituisce la traccia con la sua origine, non nuda", async () => {
    await rendiConOrigine(ORIGINE);
    expect(linkIndietro().getAttribute("href")).toBe(
      `/tracks?id=5&from=${encodeURIComponent(ORIGINE)}`);
  });

  it("senza origine torna comunque alla traccia", async () => {
    await rendiConOrigine(null);
    expect(linkIndietro().getAttribute("href")).toBe("/tracks?id=5");
  });

  it("scarta un'origine che porterebbe fuori dall'app", async () => {
    // `from` finisce dentro un href: assoluto o protocol-relative, diventerebbe
    // un'uscita dall'app confezionata da chi ha scritto l'URL.
    await rendiConOrigine("https://evil.example/x");
    expect(linkIndietro().getAttribute("href")).toBe("/tracks?id=5");
    cleanup();
    await rendiConOrigine("//evil.example/x");
    expect(linkIndietro().getAttribute("href")).toBe("/tracks?id=5");
  });

  it("la freccia c'è già mentre i simili stanno arrivando", async () => {
    // Sta in cima alla pagina, come nelle altre pagine di dettaglio, non dentro
    // l'intestazione dei risultati: così si può tornare indietro senza aspettare
    // la fine di una ricerca che dura una decina di secondi.
    discoverySimilar.mockImplementation(() => new Promise(() => {}));
    apiGet.mockResolvedValue(TRACK);
    query = new URLSearchParams(`similar=5&from=${encodeURIComponent(ORIGINE)}`);
    render(<DiscoveryPage />);

    await waitFor(() =>
      expect(screen.getByText(dict.discovery.similarBackToTrack)).toBeTruthy());
    expect(linkIndietro().getAttribute("href")).toBe(
      `/tracks?id=5&from=${encodeURIComponent(ORIGINE)}`);
    // Nessun risultato ancora: la freccia non può venire dall'intestazione.
    expect(screen.queryByLabelText(INTERRUTTORE)).toBeNull();
  });

  it("l'interruttore non perde l'origine per strada", async () => {
    // Il giro dell'interruttore riscrive l'URL: se `from` non ci sopravvive, la
    // catena si spezza al primo clic invece che al primo passo indietro.
    await rendiConOrigine(ORIGINE);
    push.mockClear();
    fireEvent.click(screen.getByLabelText(INTERRUTTORE));
    expect(push).toHaveBeenCalledWith(similarHref(5, true, ORIGINE), { scroll: false });
  });
});
