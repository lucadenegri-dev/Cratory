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
    // 11 lettere (CRATORY + DJ GOODGIRL) più lo spazio.
    expect(letters.length).toBe(12);
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

  it("copre tutte e sole le lettere di CRATORY e DJ GOODGIRL, spazio compreso", () => {
    expect(Object.keys(GLYPHS).sort().join("")).toBe(" ACDGIJLORTY");
  });

  it("lo spazio è cinque colonne vuote: separa le parole senza inchiostro", () => {
    expect(GLYPHS[" "].join("")).toBe(" ".repeat(25));
  });
});

describe("wordmarkLines (core puro)", () => {
  it("CRATORY: 5 righe da 41 colonne, tutte della stessa larghezza", () => {
    // 7 lettere da 5 colonne + 6 spazi di separazione.
    expect(WORDMARK_LINES.length).toBe(WORDMARK_ROWS);
    for (const line of WORDMARK_LINES) expect(line.length).toBe(41);
  });

  it("DJ GOODGIRL: 5 righe da 65 colonne (11 caratteri × 5 + 10 separatori)", () => {
    const lines = wordmarkLines("DJ GOODGIRL");
    expect(lines.length).toBe(WORDMARK_ROWS);
    for (const line of lines) expect(line.length).toBe(65);
    // Lo spazio fra DJ e GOODGIRL: 5 colonne del glifo + 2 separatori = 7 vuote.
    for (const line of lines) expect(line.slice(11, 18)).toBe("       ");
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

  /* L'easter egg cambia parola e titolo insieme: l'h1 nascosto deve dire ciò
     che l'arte mostra, non restare "Cratory" sotto un'altra scritta. */
  it("con word e title cambia sia l'arte sia l'h1", () => {
    const { container } = render(<AsciiWordmark word="DJ GOODGIRL" title="DJ Goodgirl" />);
    expect(screen.getByRole("heading", { level: 1, name: "DJ Goodgirl" })).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1, name: "Cratory" })).toBeNull();
    const pres = container.querySelectorAll('[aria-hidden="true"] pre');
    expect(pres.length).toBe(WORDMARK_ROWS);
    for (const pre of pres) expect(pre.textContent!.length).toBe(65);
  });
});
