import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { DiscoveryDigBar } from "@/components/discovery-dig-bar";
import type { DigSeed } from "@/lib/discovery-seeds";
import type { DiscoveryPile } from "@/lib/api/types";

afterEach(cleanup);

const OPTIONS = {
  genres: { library: ["Acid House"], styles: [] },
  labels: ["Trax Records"],
  genreCounts: [{ genre: "Acid House", count: 3 }],
};
const DEEP: DigSeed = { type: "genre", value: "Deep House" };
const pile = (value: string, total: number, reach: number): DiscoveryPile =>
  ({ seed_type: "genre", value, total, reach, resolution: total ? "style" : null });

function setup(over: Partial<React.ComponentProps<typeof DiscoveryDigBar>> = {}) {
  const props = {
    mode: "seeds" as const, onModeChange: vi.fn(),
    seeds: [DEEP], onSeedsChange: vi.fn(),
    depth: 0, onDepthChange: vi.fn(),
    source: "discogs" as const, onSourceChange: vi.fn(), discogsEnabled: true,
    stylePeriod: false, onStylePeriodChange: vi.fn(),
    options: OPTIONS, piles: null as DiscoveryPile[] | null,
    busy: false, onSubmit: vi.fn(), onSurprise: vi.fn(), canSurprise: true,
    onPickTrack: vi.fn(), searchTracks: vi.fn().mockResolvedValue([]),
    ...over,
  };
  render(<DiscoveryDigBar {...props} />);
  return props;
}

describe("DiscoveryDigBar, modo semi", () => {
  it("mostra il selettore di modo, la sorgente e la profondità", () => {
    setup();
    expect(screen.getByText("Generi ed etichette")).toBeTruthy();
    expect(screen.getByText("Traccia")).toBeTruthy();
    expect(screen.getByText("Discogs")).toBeTruthy();
    expect(screen.getByText("Superficie")).toBeTruthy();
    expect(screen.queryByLabelText(/Stile e periodo/)).toBeNull();
  });

  it("commutare il modo avvisa il chiamante", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Traccia"));
    expect(p.onModeChange).toHaveBeenCalledWith("track");
  });

  it("a Discogs spento il selettore sorgente non c'è", () => {
    setup({ discogsEnabled: false, source: "bandcamp" });
    expect(screen.queryByText("Discogs")).toBeNull();
  });

  it("Scava è disabilitato senza semi", () => {
    setup({ seeds: [] });
    expect(screen.getByText("Scava").closest("button")?.hasAttribute("disabled")).toBe(true);
  });

  it("il submit del form chiama onSubmit", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Scava"));
    expect(p.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("la profondità notifica il valore del preset", () => {
    const p = setup();
    fireEvent.click(screen.getByText("In fondo"));
    expect(p.onDepthChange).toHaveBeenCalledWith(1);
  });

  it("su pile tutte corte la profondità è inerte", () => {
    setup({ piles: [pile("Deep House", 200, 200)] });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("pila corta: tutta qui")).toBeTruthy();
  });

  it("la soglia di pila corta è il budget per seme, non 300", () => {
    // Due semi: 150 item a testa. Una pila da 200 NON è più corta.
    const seeds = [DEEP, { type: "genre" as const, value: "Electro" }];
    setup({ seeds, piles: [pile("Deep House", 200, 200), pile("Electro", 200, 200)] });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("pile tutte vuote: seme sconosciuto, non pila corta", () => {
    setup({ piles: [pile("Deep House", 0, 0)] });
    expect(screen.getByText("nessuna pila: Discogs non conosce questo seme")).toBeTruthy();
    expect(screen.queryByText("pila corta: tutta qui")).toBeNull();
  });

  it("un seme morto fra altri vivi si dice per nome", () => {
    const seeds = [DEEP, { type: "genre" as const, value: "Inesistente" }];
    setup({ seeds, piles: [pile("Deep House", 5000, 5000), pile("Inesistente", 0, 0)] });
    expect(screen.getByText(/non conosce “Inesistente”/)).toBeTruthy();
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("Sorprendimi chiama onSurprise ed è spento a pool vuoto", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Sorprendimi"));
    expect(p.onSurprise).toHaveBeenCalledTimes(1);
    cleanup();
    setup({ canSurprise: false });
    expect(screen.getByText("Sorprendimi").closest("button")?.hasAttribute("disabled")).toBe(true);
  });

  it("propaga il cambio di sorgente", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Bandcamp"));
    expect(p.onSourceChange).toHaveBeenCalledWith("bandcamp");
  });
});

describe("DiscoveryDigBar, modo traccia", () => {
  it("mostra la ricerca e l'interruttore, nasconde sorgente, profondità e bottoni", () => {
    setup({ mode: "track" });
    expect(screen.getByPlaceholderText("Cerca una traccia della libreria…")).toBeTruthy();
    expect(screen.getByLabelText(/Stile e periodo/)).toBeTruthy();
    expect(screen.queryByText("Discogs")).toBeNull();
    expect(screen.queryByText("Superficie")).toBeNull();
    expect(screen.queryByText("Scava")).toBeNull();
    expect(screen.queryByText("Sorprendimi")).toBeNull();
  });

  it("l'interruttore avvisa il chiamante", () => {
    const p = setup({ mode: "track" });
    fireEvent.click(screen.getByLabelText(/Stile e periodo/));
    expect(p.onStylePeriodChange).toHaveBeenCalledWith(true);
  });

  it("busy disabilita l'interruttore", () => {
    setup({ mode: "track", busy: true });
    expect((screen.getByLabelText(/Stile e periodo/) as HTMLInputElement).disabled).toBe(true);
  });
});
