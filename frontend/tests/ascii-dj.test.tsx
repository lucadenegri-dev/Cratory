import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AsciiDj, djFrame, DJ_ROWS, DJ_COLS, DJ_AIR_ROWS } from "@/components/dashboard/ascii-dj";

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

describe("AsciiDj (guscio)", () => {
  afterEach(cleanup);

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

  it("con onActivate è un bottone etichettato che al click chiama il gestore", () => {
    const spy = vi.fn();
    render(<AsciiDj onActivate={spy} label="Suona una traccia a caso" hint="premi" />);
    const btn = screen.getByRole("button", { name: "Suona una traccia a caso" });
    fireEvent.click(btn);
    expect(spy).toHaveBeenCalledOnce();
    expect(screen.getByText("premi")).toBeTruthy();
  });
});
