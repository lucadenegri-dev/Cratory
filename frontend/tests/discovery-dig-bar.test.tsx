import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DiscoveryDigBar } from "@/components/discovery-dig-bar";

afterEach(cleanup);

const OPTIONS = {
  genres: { library: ["Acid House"], styles: [] },
  labels: ["Trax Records"],
};

function setup(over: Partial<React.ComponentProps<typeof DiscoveryDigBar>> = {}) {
  const props = {
    subject: "", onSubjectChange: vi.fn(),
    depth: 0, onDepthChange: vi.fn(),
    options: OPTIONS, pilePages: null as number | null,
    busy: false, ready: true, onSubmit: vi.fn(),
    onSurprise: vi.fn(), canSurprise: true,
    ...over,
  };
  render(<DiscoveryDigBar {...props} />);
  return props;
}

// Storicamente il campo soggetto e il <select> del gusto condividevano il ruolo
// ARIA "combobox" e serviva disambiguare col [0]; il selettore del gusto e' stato
// rimosso (vedi test piu' sotto), ma lo helper resta come punto unico da cui i test
// prendono il campo soggetto — che e' comunque il primo nell'ordine del DOM.
function subjectInput() {
  return screen.getAllByRole("combobox")[0];
}

describe("DiscoveryDigBar", () => {
  it("suggerisce generi ed etichette nello stesso campo, generi prima", () => {
    setup();
    fireEvent.focus(subjectInput());
    const opts = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(opts[0]).toContain("Acid House");
    expect(opts[1]).toContain("Trax Records");
  });

  it("scegliere un'etichetta riporta il seed_type label", () => {
    const p = setup();
    fireEvent.focus(subjectInput());
    fireEvent.mouseDown(screen.getByText("Trax Records"));
    expect(p.onSubjectChange).toHaveBeenCalledWith("Trax Records", "label");
  });

  it("scegliere un genere riporta il seed_type genre", () => {
    const p = setup();
    fireEvent.focus(subjectInput());
    fireEvent.mouseDown(screen.getByText("Acid House"));
    expect(p.onSubjectChange).toHaveBeenCalledWith("Acid House", "genre");
  });

  it("il testo libero e' un genere", () => {
    const p = setup();
    fireEvent.change(subjectInput(), { target: { value: "Inventato" } });
    expect(p.onSubjectChange).toHaveBeenCalledWith("Inventato", "genre");
  });

  it("la profondita' notifica il valore del preset", () => {
    const p = setup();
    fireEvent.click(screen.getByText("In fondo"));
    expect(p.onDepthChange).toHaveBeenCalledWith(1);
  });

  it("su pila corta la profondita' e' inerte", () => {
    setup({ pilePages: 2 });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("pila corta: tutta qui")).toBeTruthy();
  });

  it("su pila lunga la profondita' e' attiva", () => {
    setup({ pilePages: 100 });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("pila VUOTA e pila CORTA dicono cose diverse", () => {
    // Confonderli fa dire "tutta qui" su un seme che non ha mai avuto niente: la pila
    // corta e' un seme vero con pochi dischi, la pila vuota e' un seme che Discogs non
    // conosce. In entrambi i casi la profondita' e' inerte, ma il motivo cambia.
    setup({ pilePages: 0 });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("nessuna pila: Discogs non conosce questo seme")).toBeTruthy();
    expect(screen.queryByText("pila corta: tutta qui")).toBeNull();
  });

  it("il selettore del gusto non esiste piu'", () => {
    // Riscrittura SEMANTICA dei due test sul gusto: la manopola azzerava
    // l'ordinamento in silenzio su 7 playlist su 10 (profilo quasi vuoto: etichette
    // e generi vengono dai tag dei file, che le playlist di lead non hanno). Il
    // gusto resta acceso sulla libreria, senza controllo — quindi niente <select>
    // (che avrebbe ruolo "combobox") e niente hint.
    setup();
    expect(screen.getAllByRole("combobox").length).toBe(1);   // solo il soggetto
    expect(screen.queryByText("Gusto")).toBeNull();
    expect(screen.queryByText(/Non filtra/)).toBeNull();
  });

  it("Scava e' disabilitato finche' manca il soggetto", () => {
    setup({ ready: false });
    expect(screen.getByText("Scava").closest("button")?.hasAttribute("disabled")).toBe(true);
  });

  it("suggerisce anche gli style curati, dopo le etichette", () => {
    setup({
      options: {
        ...OPTIONS,
        genres: { library: ["Acid House"], styles: ["Deep House", "Jungle"] },
      },
    });
    fireEvent.focus(subjectInput());
    const opts = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    // libreria, poi etichette, poi style curati
    expect(opts[0]).toContain("Acid House");
    expect(opts[1]).toContain("Trax Records");
    expect(opts[2]).toContain("Deep House");
    expect(opts[3]).toContain("Jungle");
  });

  it("non duplica un genere presente sia in libreria sia negli style curati", () => {
    setup({
      options: {
        ...OPTIONS,
        genres: { library: ["Acid House"], styles: ["Acid House", "Jungle"] },
      },
    });
    fireEvent.focus(subjectInput());
    const opts = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(opts.filter((o) => o.includes("Acid House"))).toHaveLength(1);
  });

  it("il click su Sorprendimi chiama onSurprise", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Sorprendimi"));
    expect(p.onSurprise).toHaveBeenCalledTimes(1);
  });

  it("Sorprendimi e' disabilitato quando il pool e' vuoto", () => {
    setup({ canSurprise: false });
    expect(screen.getByText("Sorprendimi").closest("button")?.hasAttribute("disabled")).toBe(true);
  });
});
