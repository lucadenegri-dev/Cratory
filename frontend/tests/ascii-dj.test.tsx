import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AsciiDj, djFrame, DJ_ROWS, DJ_COLS, DJ_AIR_ROWS, DJ_REST_TICK, DJ_WOOFER_ROW,
} from "@/components/dashboard/ascii-dj";

describe("djFrame (core puro)", () => {
  it("dimensioni fisse su molti tick: mai un salto di layout", () => {
    for (let t = 0; t < 200; t++) {
      const f = djFrame(t);
      expect(f.length).toBe(DJ_ROWS);
      for (const line of f) expect(line.length).toBe(DJ_COLS);
    }
  });

  it("è deterministica: stesso tick, stesso fotogramma", () => {
    expect(djFrame(42)).toEqual(djFrame(42));
  });

  it("i piatti girano: il fotogramma cambia da un tick al successivo", () => {
    expect(djFrame(0)).not.toEqual(djFrame(1));
  });

  it("il marcatore del piatto attraversa tutte e 4 le fasi in 8 tick", () => {
    // Si isola il glifo del piatto (un char di rotazione fra parentesi tonde)
    // nelle sole righe console: su 8 tick consecutivi devono comparire tutte
    // e 4 le fasi. Invariante robusto: non dipende dai glifi fissi della scena.
    const glyphs = new Set<string>();
    for (let t = 0; t < 8; t++) {
      const deck = djFrame(t).slice(DJ_AIR_ROWS).join("\n");
      const m = deck.match(/\(\s*([|/\\-])\s*\)/);
      if (m) glyphs.add(m[1]);
    }
    expect(glyphs.size).toBe(4);
  });
});

/* La cabina apre la Home, subito sotto il frontespizio, e sta ferma finché non
   parte la musica: la posa a riposo non deve mostrare un colpo di cassa.
   Ogni asserzione ha il suo denominatore sul tick in battere — senza, sarebbe
   verde anche se la posa in battere sparisse del tutto. */
describe("posa a riposo", () => {
  it("a riposo i woofer sono piccoli, al tick dopo battono", () => {
    expect(djFrame(DJ_REST_TICK)[DJ_WOOFER_ROW]).toContain("( o )");
    expect(djFrame(DJ_REST_TICK)[DJ_WOOFER_ROW]).not.toContain("( O )");
    expect(djFrame(DJ_REST_TICK + 1)[DJ_WOOFER_ROW]).toContain("( O )");
  });

  it("a riposo i tweeter sono distesi, al tick dopo compressi", () => {
    expect(djFrame(DJ_REST_TICK).join("\n")).toContain("(=====)");
    expect(djFrame(DJ_REST_TICK).join("\n")).not.toContain("(-=-=-)");
    expect(djFrame(DJ_REST_TICK + 1).join("\n")).toContain("(-=-=-)");
  });
});

describe("AsciiDj (guscio)", () => {
  afterEach(cleanup);

  it("appena montata non batte la cassa: nessuna 'O' in danger finché non suona", () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<AsciiDj animate={false} />);
      expect(container.querySelectorAll(".text-danger").length).toBe(0);

      // Denominatore: quando suona, il colpo di cassa arriva e si colora.
      cleanup();
      const playing = render(<AsciiDj animate />).container;
      act(() => { vi.advanceTimersByTime(500); });
      expect(playing.querySelectorAll(".text-danger").length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("renderizza il fotogramma in pre monospace, decorativo per gli screen reader", () => {
    const { container } = render(<AsciiDj />);
    const art = container.querySelector('[aria-hidden="true"]');
    expect(art).toBeTruthy();
    expect(art!.querySelectorAll("pre").length).toBeGreaterThan(0);
  });

  it("senza onActivate non è un bottone: solo decorazione", () => {
    render(<AsciiDj />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  /* L'etichetta esiste solo per gli assistivi: la scena non porta scritte (il
     suggerimento sotto la cabina è stato tolto, sporcava il frontespizio). */
  it("con onActivate è un bottone etichettato che al click chiama il gestore", () => {
    const spy = vi.fn();
    const { container } = render(<AsciiDj onActivate={spy} label="Suona una traccia a caso" />);
    const btn = screen.getByRole("button", { name: "Suona una traccia a caso" });
    fireEvent.click(btn);
    expect(spy).toHaveBeenCalledOnce();
    expect(container.textContent).not.toContain("Suona una traccia a caso");
  });

  /* La consolle si muove solo quando in app sta suonando qualcosa: `animate`
     è il rubinetto. Il caso `true` è il denominatore — senza, il test su
     `false` sarebbe verde anche con l'animazione rotta del tutto. */
  it("con animate la scena avanza da sola nel tempo", () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<AsciiDj animate />);
      const before = container.textContent;
      act(() => { vi.advanceTimersByTime(1500); });
      expect(container.textContent).not.toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  it("con animate={false} la scena resta ferma", () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<AsciiDj animate={false} />);
      const before = container.textContent;
      act(() => { vi.advanceTimersByTime(5000); });
      expect(container.textContent).toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  /* Fermandosi la scena conserva la posa (i piatti non tornano a capo) ma la
     cassa si rilassa: nessun woofer acceso mentre non esce suono. */
  it("fermandosi conserva la posa dei piatti ma spegne il colpo di cassa", () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(<AsciiDj animate />);
      // Si cerca un tick in battere, così il denominatore c'è davvero: senza,
      // il test sul rosso spento sarebbe verde anche partendo già spento.
      act(() => { vi.advanceTimersByTime(500); });
      if (container.querySelectorAll(".text-danger").length === 0) {
        act(() => { vi.advanceTimersByTime(500); });
      }
      expect(container.querySelectorAll(".text-danger").length).toBeGreaterThan(0);
      const platter = container.textContent!.match(/\(\s*([|/\\-])\s*\)/)?.[1];
      expect(platter).toBeTruthy();

      rerender(<AsciiDj animate={false} />);
      expect(container.querySelectorAll(".text-danger").length).toBe(0);
      expect(container.textContent!.match(/\(\s*([|/\\-])\s*\)/)?.[1]).toBe(platter);
    } finally {
      vi.useRealTimers();
    }
  });
});

/* L'easter egg (spec 2026-09-04): stessa cabina, altra figura. Le tre righe
   della DJ sono sostituzioni lunghe quanto il pezzo che rimpiazzano, quindi le
   dimensioni non cambiano e tutto il resto della scena resta identico. `boy`
   è il denominatore: senza, il test sui glifi sarebbe verde anche se `girl`
   fosse ignorata e i glifi stessero già nel template. */
describe("figura girl (easter egg)", () => {
  afterEach(cleanup);

  it("ha le stesse dimensioni di boy su molti tick", () => {
    for (let t = 0; t < 200; t++) {
      const f = djFrame(t, { figure: "girl" });
      expect(f.length).toBe(DJ_ROWS);
      for (const line of f) expect(line.length).toBe(DJ_COLS);
    }
  });

  it("porta ricci, capelli ai lati e scollo; boy no", () => {
    const girl = djFrame(DJ_REST_TICK, { figure: "girl" }).join("\n");
    const boy = djFrame(DJ_REST_TICK, { figure: "boy" }).join("\n");
    for (const piece of ["()()", "/(oo)\\", "//\\  ///"]) {
      expect(girl).toContain(piece);
      expect(boy).not.toContain(piece);
    }
    expect(boy).toContain("_(oo)_");
    expect(girl).not.toContain("_(oo)_");
  });

  it("fuori dalla figura la scena è la stessa: casse, consolle e piatti", () => {
    const girl = djFrame(DJ_REST_TICK, { figure: "girl" });
    const boy = djFrame(DJ_REST_TICK, { figure: "boy" });
    // Le righe 0 e da 4 in poi della scena (aria esclusa) non toccano la figura.
    expect(girl[DJ_AIR_ROWS]).toBe(boy[DJ_AIR_ROWS]);
    for (let r = DJ_AIR_ROWS + 4; r < DJ_ROWS; r++) expect(girl[r]).toBe(boy[r]);
  });

  it("senza opzione la figura è boy", () => {
    expect(djFrame(5)).toEqual(djFrame(5, { figure: "boy" }));
  });

  it("sbatte le ciglia anche fra i capelli", () => {
    // blink = sceneTick % 7 === 6.
    expect(djFrame(0, { sceneTick: 6, figure: "girl" }).join("\n")).toContain("/(--)\\");
    expect(djFrame(0, { sceneTick: 5, figure: "girl" }).join("\n")).toContain("/(oo)\\");
  });

  it("AsciiDj con figure=girl rende la DJ", () => {
    const { container } = render(<AsciiDj figure="girl" animate={false} />);
    expect(container.textContent).toContain("/(oo)\\");
    cleanup();
    const boy = render(<AsciiDj animate={false} />).container;
    expect(boy.textContent).toContain("_(oo)_");
  });
});
