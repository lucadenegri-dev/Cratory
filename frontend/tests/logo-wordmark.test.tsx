import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GLYPHS, GLYPH_FILL_RULE } from "@/components/dashboard/logo-glyphs";
import {
  CAP_HEIGHT, LogoWordmark, SPACE_ADVANCE, TRACKING, letterOpacity, wordmarkLayout,
} from "@/components/dashboard/logo-wordmark";

/* I glifi sono generati dai file in assets/branding/alfabeto-corrosione/svg:
   il test sorveglia cio' che il compositore da' per scontato di loro. */
describe("GLYPHS (l'alfabeto Corrosione)", () => {
  it("copre tutte e sole le lettere di CRATORY e DJ GOODGIRL", () => {
    expect(Object.keys(GLYPHS).sort().join("")).toBe("ACDGIJLORTY");
  });

  it("ogni glifo ha un tracciato disegnato e un ingombro positivo", () => {
    const voci = Object.entries(GLYPHS);
    // Denominatore: con un dizionario vuoto il ciclo sarebbe verde a vuoto.
    expect(voci.length).toBe(11);
    for (const [ch, g] of voci) {
      expect(g.d.startsWith("M"), `${ch}: il tracciato parte da un M`).toBe(true);
      // I file sorgente non chiudono con Z: il riempimento chiude da se'. Cio'
      // che conta e' che ci sia del disegno, non solo un punto di partenza.
      expect(g.d, `${ch}: ha delle curve`).toMatch(/[CL]/);
      expect(g.w, `${ch}: larghezza`).toBeGreaterThan(0);
      expect(g.h, `${ch}: altezza`).toBeGreaterThan(0);
    }
  });

  /* Regressione: il generatore prendeva solo `d` e lasciava indietro la
     fill-rule dei file sorgente. Senza, la O si riempie e diventa un rombo. */
  it("la regola di riempimento arriva fino al componente", () => {
    expect(GLYPH_FILL_RULE).toBe("evenodd");
    const { container } = render(<LogoWordmark />);
    expect(container.querySelector("svg")!.getAttribute("fill-rule")).toBe("evenodd");
    cleanup();
  });

  it("nessun colore scritto nel tracciato: la scritta segue il tema", () => {
    // Un `fill` fisso qui dentro renderebbe la parola invisibile su fondo scuro.
    for (const [ch, g] of Object.entries(GLYPHS)) {
      expect(g.d, `${ch}`).not.toMatch(/fill|#[0-9a-f]{3,6}/i);
    }
  });
});

describe("wordmarkLayout (il compositore)", () => {
  it("porta ogni lettera alla stessa altezza senza deformarla", () => {
    const { items, height } = wordmarkLayout("CRATORY");
    expect(items.length).toBe(7);
    expect(height).toBe(CAP_HEIGHT);
    for (const it of items) {
      // Altezza pareggiata...
      expect(it.glyph.h * it.scale).toBeCloseTo(CAP_HEIGHT, 6);
      // ...e scala UNIFORME: la larghezza segue la stessa scala dell'altezza,
      // che e' cio' che distingue «ingrandire» da «stirare».
      expect(it.width).toBeCloseTo(it.glyph.w * it.scale, 6);
    }
    // Le lettere hanno proporzioni diverse, quindi larghezze diverse: se
    // uscissero tutte uguali vorrebbe dire che le stiamo deformando.
    expect(new Set(items.map((i) => Math.round(i.width))).size).toBeGreaterThan(1);
  });

  it("le dispone da sinistra a destra, con l'aria richiesta fra una e l'altra", () => {
    const { items, width } = wordmarkLayout("CRAT", 100);
    const bordi = items.map((i) => i.x + (i.glyph.w === 0 ? 0 : 0));
    for (let k = 1; k < bordi.length; k++) {
      expect(bordi[k], `lettera ${k}`).toBeGreaterThan(bordi[k - 1]);
    }
    const somma = items.reduce((t, i) => t + i.width, 0) + 100 * (items.length - 1);
    expect(width).toBeCloseTo(somma, 6);
  });

  it("lo spazio avanza senza disegnare nulla", () => {
    const senza = wordmarkLayout("DJ");
    const con = wordmarkLayout("D J");
    expect(con.items.length).toBe(senza.items.length);   // lo spazio non e' un glifo
    expect(con.width).toBeCloseTo(senza.width + SPACE_ADVANCE + TRACKING, 6);
  });

  it("rifiuta una lettera che non ha glifo invece di comporre una parola monca", () => {
    expect(() => wordmarkLayout("CRATORYX")).toThrow(/nessun glifo per "X"/);
  });

  it("compone anche l'easter egg", () => {
    expect(() => wordmarkLayout("DJ GOODGIRL")).not.toThrow();
    // Piu' lunga di CRATORY: a parita' di larghezza a schermo si disegnera'
    // piu' bassa da se', che e' il motivo per cui non serve piu' un corpo
    // per persona.
    expect(wordmarkLayout("DJ GOODGIRL").width)
      .toBeGreaterThan(wordmarkLayout("CRATORY").width);
  });
});

describe("letterOpacity (l'ingresso)", () => {
  it("a ingresso finito sono tutte piene", () => {
    for (let i = 0; i < 7; i++) expect(letterOpacity(i, 7, 1)).toBe(1);
  });

  it("a ingresso fermo sulla partenza solo la prima ha gia' cominciato", () => {
    expect(letterOpacity(0, 7, 0)).toBe(0);
    expect(letterOpacity(6, 7, 0)).toBe(0);
  });

  it("le lettere entrano in ordine: nessuna precede quella prima di lei", () => {
    for (const p of [0.1, 0.3, 0.5, 0.8]) {
      for (let i = 1; i < 7; i++) {
        expect(letterOpacity(i, 7, p), `p=${p} lettera ${i}`)
          .toBeLessThanOrEqual(letterOpacity(i - 1, 7, p));
      }
    }
  });

  it("a meta' strada le lettere sono a punti diversi dell'entrata", () => {
    // Senza questo, un'implementazione che restituisse sempre 0 (o sempre 1)
    // passerebbe le prove qui sopra: quelle guardano solo l'ordine.
    const meta = Array.from({ length: 7 }, (_, i) => letterOpacity(i, 7, 0.5));
    expect(meta[0]).toBeGreaterThan(0);          // la prima e' gia' in arrivo
    expect(meta[6]).toBeLessThan(meta[0]);       // l'ultima e' indietro
    expect(new Set(meta).size).toBeGreaterThan(1);
  });
});

describe("LogoWordmark (guscio)", () => {
  afterEach(cleanup);

  it("da' alla Home il titolo che le manca, e marca l'arte come decorativa", () => {
    const { container } = render(<LogoWordmark />);
    expect(screen.getByRole("heading", { level: 1, name: "Cratory" })).toBeTruthy();
    const svg = container.querySelector('svg[aria-hidden="true"]');
    expect(svg).toBeTruthy();
    expect(svg!.querySelectorAll("path").length).toBe(7);
    // Il colore viene dal testo: e' cio' che la fa vivere su entrambi i temi.
    expect(svg!.getAttribute("fill")).toBe("currentColor");
  });

  it("con word e title cambia sia l'arte sia l'h1", () => {
    const { container } = render(<LogoWordmark word="DJ GOODGIRL" title="DJ Goodgirl" />);
    expect(screen.getByRole("heading", { level: 1, name: "DJ Goodgirl" })).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1, name: "Cratory" })).toBeNull();
    // 10 lettere: lo spazio non disegna.
    expect(container.querySelectorAll("svg path").length).toBe(10);
  });
});
