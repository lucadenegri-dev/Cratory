import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  AsciiWordmark, GLYPHS, WORDMARK_LINES, WORDMARK_ROWS, wordmarkLines,
} from "@/components/dashboard/ascii-wordmark";

/* La geometria dei glifi è ciò che tiene in riga le colonne: il core non pareggia
   le righe a valle, quindi l'invariante deve mordere qui. */
describe("GLYPHS (l'alfabeto)", () => {
  it("ogni lettera è WORDMARK_ROWS righe da 5 caratteri", () => {
    const letters = Object.entries(GLYPHS);
    // Denominatore: se il dizionario si svuotasse, il forEach sarebbe verde a vuoto.
    expect(letters.length).toBe(6);
    for (const [ch, glyph] of letters) {
      expect(glyph.length, `${ch}: numero di righe`).toBe(WORDMARK_ROWS);
      for (const row of glyph) expect(row.length, `${ch}: riga "${row}"`).toBe(5);
    }
  });

  it("solo '#' e spazio: nessun glifo unicode che cadrebbe sul font di fallback", () => {
    for (const [ch, glyph] of Object.entries(GLYPHS)) {
      expect(glyph.join(""), `${ch}`).toMatch(/^[# ]+$/);
    }
  });

  it("copre tutte e sole le lettere di CRATORY", () => {
    expect(Object.keys(GLYPHS).sort().join("")).toBe("ACORTY");
  });
});

describe("wordmarkLines (core puro)", () => {
  it("CRATORY: 5 righe da 41 colonne, tutte della stessa larghezza", () => {
    // 7 lettere da 5 colonne + 6 spazi di separazione.
    expect(WORDMARK_LINES.length).toBe(WORDMARK_ROWS);
    for (const line of WORDMARK_LINES) expect(line.length).toBe(41);
  });

  it("separa le lettere con una sola colonna di spazio", () => {
    // La riga 0 di C e di R sono "#####" e "#### ": affiancate danno questo.
    expect(wordmarkLines("CR")[0]).toBe("##### #### ");
  });

  it("rifiuta una lettera senza glifo invece di comporre righe monche", () => {
    expect(() => wordmarkLines("CRATORYX")).toThrow(/nessun glifo per "X"/);
  });
});

describe("AsciiWordmark (guscio)", () => {
  afterEach(cleanup);

  it("dà alla Home il titolo che le manca, e marca l'arte come decorativa", () => {
    const { container } = render(<AsciiWordmark />);
    expect(screen.getByRole("heading", { level: 1, name: "Cratory" })).toBeTruthy();
    const art = container.querySelector('[aria-hidden="true"]');
    expect(art).toBeTruthy();
    expect(art!.querySelectorAll("pre").length).toBe(WORDMARK_ROWS);
  });
});
