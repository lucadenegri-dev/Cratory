import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DiscoveryDigBar } from "@/components/discovery-dig-bar";

afterEach(cleanup);

const OPTIONS = {
  genres: { library: ["Acid House"], styles: [] },
  labels: ["Trax Records"],
  playlists: [{ id: 1, name: "Warmup" }],
};

function setup(over: Partial<React.ComponentProps<typeof DiscoveryDigBar>> = {}) {
  const props = {
    subject: "", onSubjectChange: vi.fn(),
    depth: 0, onDepthChange: vi.fn(),
    tasteRef: null, onTasteRefChange: vi.fn(),
    options: OPTIONS, pilePages: null as number | null,
    busy: false, ready: true, onSubmit: vi.fn(),
    ...over,
  };
  render(<DiscoveryDigBar {...props} />);
  return props;
}

// Il campo soggetto e il <select> nativo del gusto condividono entrambi il
// ruolo ARIA "combobox" (implicito su <select> senza multiple): con le
// playlist di default presenti, getByRole("combobox") e' ambiguo. Il campo
// soggetto e' sempre il primo nell'ordine del DOM (zona 1 della riga).
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
  });

  it("su pila lunga la profondita' e' attiva", () => {
    setup({ pilePages: 100 });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("il gusto sparisce se non ci sono playlist", () => {
    setup({ options: { ...OPTIONS, playlists: [] } });
    expect(screen.queryByText("Gusto")).toBeNull();
    // l'hint di onesta' e' agganciato allo stesso controllo: sparisce con lui
    expect(screen.queryByText(/Non filtra/)).toBeNull();
  });

  it("l'hint del gusto dichiara che non filtra, quando il gusto c'e'", () => {
    setup();
    expect(screen.getByText(/Non filtra/)).toBeTruthy();
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
});
