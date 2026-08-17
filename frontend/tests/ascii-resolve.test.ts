import { describe, expect, it } from "vitest";

import { easeOutQuart, resolveLines } from "@/lib/ascii-resolve";
import { fallPeak, formatHz } from "@/components/dashboard/spectrum-strip";
import { airParticles } from "@/components/dashboard/ascii-atmosphere";
import { WORDMARK_LINES } from "@/components/dashboard/ascii-wordmark";

/* La larghezza costante è l'invariante che tiene: l'ingresso gira dentro una
   composizione a piena altezza, e una riga più lunga o più corta di un solo
   carattere farebbe saltare l'impaginazione a metà animazione. */
describe("resolveLines", () => {
  const lines = ["abc def", "ghijklm", "   x   "];

  it("conserva il numero di righe e la larghezza a ogni progresso", () => {
    for (const p of [0, 0.13, 0.5, 0.87, 1]) {
      const out = resolveLines(lines, p);
      expect(out.length, `p=${p}`).toBe(lines.length);
      out.forEach((l, i) => expect(l.length, `p=${p} riga ${i}`).toBe(lines[i].length));
    }
  });

  it("a progresso 1 è il disegno originale, a 0 non lo è ancora", () => {
    expect(resolveLines(lines, 1)).toEqual(lines);
    // Denominatore: senza questo il test sopra sarebbe verde anche se la
    // funzione restituisse sempre l'originale, cioè senza alcun effetto.
    expect(resolveLines(lines, 0)).not.toEqual(lines);
  });

  /* Il bug che questo test blocca: l'hash a 32 bit tornava negativo dopo
     l'ultimo XOR, l'indice del glifo finiva fuori dalla stringa di rumore e la
     riga si riempiva della parola "undefined" — larghezza esplosa compresa. */
  it("non emette mai caratteri fuori dall'alfabeto: nessun 'undefined' nelle righe", () => {
    const allowed = new Set([...lines.join(""), ...`#/\\|-=+*:.·°`]);
    for (let i = 0; i <= 20; i++) {
      for (const line of resolveLines(lines, i / 20)) {
        for (const ch of line) expect(allowed.has(ch), `carattere "${ch}" a p=${i / 20}`).toBe(true);
      }
    }
  });

  it("è deterministica e monotona: una cella risolta non torna rumore", () => {
    expect(resolveLines(lines, 0.4)).toEqual(resolveLines(lines, 0.4));
    const early = resolveLines(lines, 0.35);
    const late = resolveLines(lines, 0.75);
    let resolvedEarly = 0;
    for (let r = 0; r < lines.length; r++) {
      for (let c = 0; c < lines[r].length; c++) {
        if (early[r][c] === lines[r][c] && lines[r][c] !== " ") {
          resolvedEarly++;
          expect(late[r][c]).toBe(lines[r][c]);
        }
      }
    }
    expect(resolvedEarly).toBeGreaterThan(0);   // denominatore
  });

  it("regge il frontespizio vero senza deformarlo", () => {
    for (const l of resolveLines(WORDMARK_LINES, 0.5)) expect(l.length).toBe(41);
  });
});

describe("easeOutQuart", () => {
  it("blocca il dominio e sale senza superare 1", () => {
    expect(easeOutQuart(-1)).toBe(0);
    expect(easeOutQuart(0)).toBe(0);
    expect(easeOutQuart(1)).toBe(1);
    expect(easeOutQuart(2)).toBe(1);
    // Parte veloce: a metà tempo è già oltre l'80% del percorso.
    expect(easeOutQuart(0.5)).toBeGreaterThan(0.8);
  });
});

/* L'asse della striscia spettro porta gli estremi veri della scala: senza
   numeri leggibili le barre non dicono cosa rappresentano. */
describe("formatHz", () => {
  it("formatta gli hertz dell'asse: interi sotto il kilo, kHz sopra", () => {
    expect(formatHz(46.9)).toBe("47 Hz");
    expect(formatHz(999)).toBe("999 Hz");
    expect(formatHz(1000)).toBe("1 kHz");
    expect(formatHz(10312)).toBe("10.3 kHz");
  });
});

/* La tacca di picco dei VU meter: il segnale la spinge su all'istante, la
   caduta è lenta e costante. L'invariante che conta: mai sotto la barra. */
describe("fallPeak", () => {
  it("sale subito col segnale e non sta mai sotto la barra", () => {
    expect(fallPeak(0.2, 0.9)).toBe(0.9);        // salita istantanea
    expect(fallPeak(0.9, 0.899)).toBeLessThan(0.9); // sopra la barra scende...
    expect(fallPeak(0.9, 0.899)).toBeGreaterThanOrEqual(0.899); // ...mai sotto
  });

  it("scende a passo costante e si ferma a zero", () => {
    const one = fallPeak(0.5, 0);
    expect(one).toBeLessThan(0.5);
    // Denominatore del "costante": due passi consecutivi tolgono lo stesso.
    expect(0.5 - one).toBeCloseTo(one - fallPeak(one, 0), 10);
    let v = 0.02;
    for (let i = 0; i < 10; i++) v = fallPeak(v, 0);
    expect(v).toBe(0);
  });
});

/* Il campo dell'aria è derivato dall'indice, mai da Math.random: server e
   client devono generare lo stesso pulviscolo, altrimenti l'hydration se ne
   accorge e React ributta via il markup. */
describe("airParticles", () => {
  it("è deterministico e non usa il caso", () => {
    expect(airParticles(12)).toEqual(airParticles(12));
    // Denominatore: due semi diversi devono davvero dare campi diversi.
    expect(airParticles(12)).not.toEqual(airParticles(12, 5));
  });

  it("tiene ogni particella dentro i limiti della composizione", () => {
    const ps = airParticles(60);
    expect(ps.length).toBe(60);
    for (const p of ps) {
      expect(p.left).toBeGreaterThanOrEqual(2);
      expect(p.left).toBeLessThanOrEqual(98);
      expect(p.top).toBeGreaterThanOrEqual(0);
      expect(p.top).toBeLessThanOrEqual(100);
      expect(p.duration).toBeGreaterThanOrEqual(16);
      expect(p.delay).toBeLessThanOrEqual(0);          // entra già a metà corsa
      expect(Math.abs(p.delay)).toBeLessThanOrEqual(p.duration);
      expect(p.glyph).toMatch(/^[°*·.',]$/);           // solo glifi di DM Mono
    }
  });

  it("distribuisce le quote invece di ammucchiarle a metà", () => {
    const tops = airParticles(40).map((p) => p.top);
    expect(Math.min(...tops)).toBeLessThan(25);
    expect(Math.max(...tops)).toBeGreaterThan(75);
  });
});
