# DJ GOODGIRL Easter Egg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando l'username SoundCloud salvato è `xgiorgix`, il frontespizio della Home dice DJ GOODGIRL, la DJ nella cabina ascii è una ragazza riccia e il pulviscolo che sale con la musica contiene cuori. Per chiunque altro, la Home è identica a oggi.

**Architecture:** Tutto frontend. Un helper puro `personaFor(username)` decide la persona (`"cratory" | "goodgirl"`) leggendo l'username da `GET /api/soundcloud/status`, già esposto. La Home monta il frontespizio solo a persona nota (niente lampeggio) e passa la persona ai tre componenti d'arte come prop con default che lasciano tutto com'è: `AsciiWordmark` (`word`, `title`), `AsciiDj` (`figure`), `AsciiAtmosphere` (`hearts`). I core deterministici (`wordmarkLines`, `djFrame`, `airParticles`) restano puri e testati.

**Tech Stack:** Next.js 16 (App Router), React, Tailwind, vitest + @testing-library/react. Spec: `docs/superpowers/specs/2026-09-04-dj-goodgirl-easter-egg-design.md`.

## Global Constraints

- Nell'arte a griglia (scritta e cabina) solo glifi presenti in DM Mono: `#`, spazio, `( ) / \ o -`. Nessun unicode lì. Il cuore `♥` è ammesso **solo** nel pulviscolo (`AsciiAtmosphere`), dove ogni particella è posizionata da sola.
- Ogni sostituzione nel template della cabina è lunga esattamente quanto il pezzo che rimpiazza, agganciata con `indexOf`: `DJ_COLS` e `DJ_ROWS` non cambiano.
- L'username che accende l'easter egg è `xgiorgix`, confronto senza distinzione di maiuscole.
- Testi: scritta `DJ GOODGIRL`, h1 nascosto `DJ Goodgirl`. Nessuna chiave i18n nuova.
- Nessuna modifica a backend, Impostazioni, Tauri.
- Commit senza `Co-Authored-By` (preferenza dell'utente). Messaggi in italiano, prefisso `feat(home):` / `test(home):` / `docs:`.
- Il worktree non ha `node_modules`: Task 1 lo installa per davvero (`npm ci`), non con un symlink (un symlink rompe Turbopack per `next dev`/`build`).
- Comandi frontend dalla cartella `frontend` del worktree: `npx vitest run <file>` per un file, `npm run test:unit` per tutto, `npm run lint`, `npm run build`.

---

### Task 1: Ambiente del worktree e helper `personaFor`

**Files:**
- Create: `frontend/lib/persona.ts`
- Create: `frontend/tests/persona.test.ts`

**Interfaces:**
- Consumes: niente.
- Produces: `export type Persona = "cratory" | "goodgirl"` e `export function personaFor(username: string | null | undefined): Persona`. Task 5 li importa da `@/lib/persona`.

- [ ] **Step 1: Installare le dipendenze del frontend nel worktree**

Run (dalla radice del worktree):
```bash
cd frontend && npm ci
```
Expected: termina senza errori, esiste `frontend/node_modules`. `git status --porcelain` non mostra nulla (`/node_modules` è in `.gitignore`).

- [ ] **Step 2: Scrivere il test che fallisce**

`frontend/tests/persona.test.ts`:
```ts
import { describe, expect, it } from "vitest";

import { personaFor } from "@/lib/persona";

/* L'easter egg si accende su un solo username. Il denominatore è il caso
   positivo: senza, ogni "cratory" sarebbe verde anche con la funzione vuota. */
describe("personaFor", () => {
  it("xgiorgix accende la persona goodgirl, in qualunque maiuscola", () => {
    expect(personaFor("xgiorgix")).toBe("goodgirl");
    expect(personaFor("XGIORGIX")).toBe("goodgirl");
  });

  it("tutto il resto è cratory", () => {
    expect(personaFor(null)).toBe("cratory");
    expect(personaFor(undefined)).toBe("cratory");
    expect(personaFor("")).toBe("cratory");
    expect(personaFor("giorgia")).toBe("cratory");
    expect(personaFor("xgiorgix2")).toBe("cratory");
  });
});
```

- [ ] **Step 3: Eseguire il test e vederlo fallire**

Run: `cd frontend && npx vitest run tests/persona.test.ts`
Expected: FAIL, `Failed to resolve import "@/lib/persona"`.

- [ ] **Step 4: Implementare l'helper**

`frontend/lib/persona.ts`:
```ts
/* La persona del frontespizio della Home (spec 2026-09-04): un easter egg.
   Con l'username SoundCloud salvato in Impostazioni uguale a `xgiorgix` la
   Home dice DJ GOODGIRL e la DJ nella cabina è una ragazza; per chiunque
   altro resta CRATORY. La decisione è tutta qui, pura e senza React, così la
   Home la applica e i test la coprono senza montare nulla. */

export type Persona = "cratory" | "goodgirl";

const GOODGIRL_USERNAME = "xgiorgix";

/** `username` è quello di `GET /api/soundcloud/status` (già senza `@` e
 *  spazi ai bordi: li toglie il backend al salvataggio). */
export function personaFor(username: string | null | undefined): Persona {
  return (username ?? "").trim().toLowerCase() === GOODGIRL_USERNAME ? "goodgirl" : "cratory";
}
```

- [ ] **Step 5: Eseguire il test e vederlo passare**

Run: `cd frontend && npx vitest run tests/persona.test.ts`
Expected: PASS, 2 test.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/persona.ts frontend/tests/persona.test.ts
git commit -m "feat(home): personaFor, l'interruttore dell'easter egg DJ GOODGIRL"
```

---

### Task 2: La scritta — glifi nuovi e prop `word`/`title`

**Files:**
- Modify: `frontend/components/dashboard/ascii-wordmark.tsx`
- Modify: `frontend/tests/ascii-wordmark.test.tsx`

**Interfaces:**
- Consumes: niente.
- Produces: `AsciiWordmark({ word?: string; title?: string; sizeClass?: string })`, default `word = "CRATORY"`, `title = "Cratory"`. `GLYPHS` copre `ACDGIJLORTY` più lo spazio. Task 5 passa `word="DJ GOODGIRL" title="DJ Goodgirl"`.

- [ ] **Step 1: Aggiornare i test (falliranno)**

In `frontend/tests/ascii-wordmark.test.tsx` sostituire l'intero blocco `describe("GLYPHS (l'alfabeto)", …)` con:

```tsx
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
```

Nel blocco `describe("wordmarkLines (core puro)", …)` aggiungere, dopo il test "CRATORY: 5 righe da 41 colonne…":

```tsx
  it("DJ GOODGIRL: 5 righe da 65 colonne (11 caratteri × 5 + 10 separatori)", () => {
    const lines = wordmarkLines("DJ GOODGIRL");
    expect(lines.length).toBe(WORDMARK_ROWS);
    for (const line of lines) expect(line.length).toBe(65);
    // Lo spazio fra DJ e GOODGIRL: 5 colonne del glifo + 2 separatori = 7 vuote.
    for (const line of lines) expect(line.slice(11, 18)).toBe("       ");
  });
```

Sostituire il blocco `describe("AsciiWordmark (guscio)", …)` con:

```tsx
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
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `cd frontend && npx vitest run tests/ascii-wordmark.test.tsx`
Expected: FAIL su "ogni lettera…" (6 ≠ 12), "copre tutte e sole…", "lo spazio…", "DJ GOODGIRL: 5 righe…" (throw `nessun glifo per "D"`), "con word e title…".

- [ ] **Step 3: Implementare glifi e prop**

In `frontend/components/dashboard/ascii-wordmark.tsx`:

Sostituire il commento e la costante `GLYPHS` (da `/* Glifi 5x5, solo le lettere che servono a CRATORY` fino alla chiusura `};` di `Y`) con:

```tsx
/* Glifi 5x5, solo le lettere che servono: CRATORY e, per l'easter egg (spec
   2026-09-04), DJ GOODGIRL. Un alfabeto completo sarebbe codice mai chiamato.
   Lo spazio è un glifo come gli altri: cinque colonne vuote, così la parola
   composta ha larghezza uniforme senza casi speciali nel compositore.
   Esportati perché il test ne sorvegli la geometria, che è ciò che tiene in
   riga le colonne. */
export const GLYPHS: Record<string, readonly string[]> = {
  C: ["#####",
      "#    ",
      "#    ",
      "#    ",
      "#####"],
  R: ["#### ",
      "#   #",
      "#### ",
      "#  # ",
      "#   #"],
  A: [" ### ",
      "#   #",
      "#####",
      "#   #",
      "#   #"],
  T: ["#####",
      "  #  ",
      "  #  ",
      "  #  ",
      "  #  "],
  O: [" ### ",
      "#   #",
      "#   #",
      "#   #",
      " ### "],
  Y: ["#   #",
      " # # ",
      "  #  ",
      "  #  ",
      "  #  "],
  D: ["#### ",
      "#   #",
      "#   #",
      "#   #",
      "#### "],
  J: ["#####",
      "    #",
      "    #",
      "#   #",
      " ### "],
  G: [" ####",
      "#    ",
      "# ###",
      "#   #",
      " ####"],
  I: ["#####",
      "  #  ",
      "  #  ",
      "  #  ",
      "#####"],
  L: ["#    ",
      "#    ",
      "#    ",
      "#    ",
      "#####"],
  " ": ["     ",
        "     ",
        "     ",
        "     ",
        "     "],
};
```

Aggiungere `useMemo` all'import di React in testa al file (dopo `"use client";`):

```tsx
import { useMemo } from "react";
```

Sostituire la firma e le prime due righe del componente `AsciiWordmark`:

```tsx
export function AsciiWordmark({ sizeClass }: { sizeClass?: string } = {}) {
  const intro = useAsciiIntro();
  const lines = resolveLines(WORDMARK_LINES, intro);
  return (
    <div className="flex justify-center overflow-x-auto overflow-y-hidden">
      <h1 className="sr-only">Cratory</h1>
```

con:

```tsx
export function AsciiWordmark({ word = WORD, title = "Cratory", sizeClass }: {
  /** La parola composta dai glifi. L'easter egg passa "DJ GOODGIRL". */
  word?: string;
  /** Il testo dell'h1 nascosto: deve dire ciò che l'arte mostra. */
  title?: string;
  sizeClass?: string;
} = {}) {
  const intro = useAsciiIntro();
  const base = useMemo(() => (word === WORD ? WORDMARK_LINES : wordmarkLines(word)), [word]);
  const lines = resolveLines(base, intro);
  return (
    <div className="flex justify-center overflow-x-auto overflow-y-hidden">
      <h1 className="sr-only">{title}</h1>
```

Aggiornare il commento di apertura del componente (`/** Il frontespizio: la parola in grande, ferma. …`) aggiungendo in coda, prima della chiusura `*/`:

```
 *  `word` e `title` esistono per l'easter egg DJ GOODGIRL (spec 2026-09-04):
 *  la Home li passa insieme, i default lasciano CRATORY.
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `cd frontend && npx vitest run tests/ascii-wordmark.test.tsx`
Expected: PASS, 9 test.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/ascii-wordmark.tsx frontend/tests/ascii-wordmark.test.tsx
git commit -m "feat(home): la scritta accetta word/title, alfabeto esteso a DJ GOODGIRL"
```

---

### Task 3: La cabina — figura `girl`

**Files:**
- Modify: `frontend/components/dashboard/ascii-dj.tsx`
- Modify: `frontend/tests/ascii-dj.test.tsx`

**Interfaces:**
- Consumes: niente.
- Produces: `export type DjFigure = "boy" | "girl"`; `djFrame(tick, opts?: { sceneTick?: number; thump?: boolean; figure?: DjFigure })`; prop `figure?: DjFigure` su `AsciiDj` (default `"boy"`). Task 5 passa `figure`.

- [ ] **Step 1: Scrivere i test che falliscono**

In `frontend/tests/ascii-dj.test.tsx`, aggiornare l'import:

```tsx
import {
  AsciiDj, djFrame, DJ_ROWS, DJ_COLS, DJ_AIR_ROWS, DJ_REST_TICK, DJ_WOOFER_ROW,
} from "@/components/dashboard/ascii-dj";
```

resta com'è (i nomi bastano). Aggiungere in fondo al file:

```tsx
/* L'easter egg (spec 2026-09-04): stessa cabina, altra figura. Le tre righe
   della DJ sono sostituzioni lunghe quanto il pezzo che rimpiazzano, quindi le
   dimensioni non cambiano e tutto il resto della scena resta identico. `boy`
   è il denominatore: senza, il test sui glifi sarebbe verde anche se `girl`
   fosse ignorata e i glifi stessero già nel template. */
describe("figura girl (easter egg)", () => {
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
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `cd frontend && npx vitest run tests/ascii-dj.test.tsx`
Expected: FAIL nei test del blocco "figura girl" (TypeScript non blocca vitest; a runtime `figure` è ignorata e i glifi mancano). Gli altri test restano PASS.

- [ ] **Step 3: Implementare la figura**

In `frontend/components/dashboard/ascii-dj.tsx`:

Dopo la costante `SCENE` (chiusura `];`) e prima di `export const DJ_AIR_ROWS = 3;` aggiungere:

```tsx
export type DjFigure = "boy" | "girl";

/* La DJ dell'easter egg (spec 2026-09-04): stessa cabina, tre righe della
   figura ritoccate — ricci in testa, capelli ai lati del viso, scollo a V fra
   le braccia. Ogni pezzo è lungo quanto quello che rimpiazza e si aggancia
   con indexOf sul template di base, come le parti animate: l'allineamento non
   può rompersi. La consolle sotto resta quella di sempre. */
const GIRL_SCENE = ((): string[] => {
  const s = SCENE.slice();
  const face = s[2].indexOf("(oo)");
  s[1] = splice(s[1], face, "()()");                       // sopra, al posto di "///"
  s[2] = splice(s[2], face - 1, "/(oo)\\");               // "_(oo)_" → "/(oo)\"
  s[3] = splice(s[3], s[3].indexOf("//    //"), "//\\  ///");
  return s;
})();
```

`splice` è una `function` dichiarata più sotto: viene sollevata, quindi è già disponibile qui.

Sostituire il blocco `const AT = { … };` (con il commento che lo precede) con:

```tsx
/* Le posizioni delle parti animate, trovate una volta sola per template. I
   capelli non ci sono: restano quelli del template, fermi. */
function locate(scene: readonly string[]) {
  return {
    tweetL: scene[1].indexOf("(=====)"),
    tweetR: scene[1].lastIndexOf("(=====)"),
    face: scene[2].indexOf("(oo)"),
    woofL: scene[5].indexOf("( O )"),
    woofR: scene[5].lastIndexOf("( O )"),
    platL: scene[6].indexOf("( o )"),
    platR: scene[6].lastIndexOf("( o )"),
    wave1: scene[6].indexOf("^^^"),
    slash1: scene[6].indexOf("///"),
    wave2: scene[7].indexOf("^^^"),
    slash2: scene[7].indexOf("///"),
  };
}

const FIGURES: Record<DjFigure, { scene: readonly string[]; at: ReturnType<typeof locate> }> = {
  boy: { scene: SCENE, at: locate(SCENE) },
  girl: { scene: GIRL_SCENE, at: locate(GIRL_SCENE) },
};
```

Nella firma di `djFrame` sostituire:

```tsx
export function djFrame(tick: number, opts?: { sceneTick?: number; thump?: boolean }): string[] {
```

con:

```tsx
export function djFrame(
  tick: number,
  opts?: { sceneTick?: number; thump?: boolean; figure?: DjFigure },
): string[] {
```

e aggiungere al commento JSDoc di `djFrame`, prima della chiusura `*/`:

```
 *  `figure` sceglie chi sta dietro la consolle (default `boy`; `girl` è
 *  l'easter egg DJ GOODGIRL). */
```

Nel corpo di `djFrame` sostituire:

```tsx
  const scene = SCENE.slice();
```

con:

```tsx
  const { scene: base, at: AT } = FIGURES[opts?.figure ?? "boy"];
  const scene = base.slice();
```

In `AsciiDj`, aggiungere la prop: sostituire

```tsx
export function AsciiDj({ onActivate, label, animate = true, sizeClass }: {
  onActivate?: () => void;
  label?: string;
  animate?: boolean;
```

con:

```tsx
export function AsciiDj({ onActivate, label, animate = true, sizeClass, figure = "boy" }: {
  onActivate?: () => void;
  label?: string;
  animate?: boolean;
  /** Chi sta dietro la consolle: `girl` è l'easter egg DJ GOODGIRL. */
  figure?: DjFigure;
```

e nella chiamata a `djFrame` dentro `AsciiDj` sostituire:

```tsx
    djFrame(reduced ? DJ_REST_TICK : air, {
      sceneTick: reduced ? DJ_REST_TICK : tick,
```

con:

```tsx
    djFrame(reduced ? DJ_REST_TICK : air, {
      figure,
      sceneTick: reduced ? DJ_REST_TICK : tick,
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `cd frontend && npx vitest run tests/ascii-dj.test.tsx`
Expected: PASS, tutti (i 12 di prima più 6 nuovi).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/ascii-dj.tsx frontend/tests/ascii-dj.test.tsx
git commit -m "feat(home): la cabina accetta figure=girl, la DJ riccia dell'easter egg"
```

---

### Task 4: I cuori nel pulviscolo

**Files:**
- Modify: `frontend/components/dashboard/ascii-atmosphere.tsx`
- Modify: `frontend/app/globals.css` (dopo la riga `.air-near { color: var(--c-fg); }`)
- Create: `frontend/tests/ascii-atmosphere.test.tsx`

**Interfaces:**
- Consumes: niente.
- Produces: `AsciiAtmosphere({ active: boolean; hearts?: boolean })`; `export const HEART = "♥"`; `export const HEART_GLYPHS`; `airParticles(count, seed = 0, glyphs: readonly string[] = GLYPHS)`. Task 5 passa `hearts`.

- [ ] **Step 1: Scrivere il test che fallisce**

`frontend/tests/ascii-atmosphere.test.tsx`:
```tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  AsciiAtmosphere, airParticles, HEART, HEART_GLYPHS,
} from "@/components/dashboard/ascii-atmosphere";

/* I cuori dell'easter egg (spec 2026-09-04) stanno nel pulviscolo, che si vede
   solo mentre suona. La tavolozza di default è il denominatore: senza, un
   campo fatto tutto di cuori passerebbe il test sui cuori. */
describe("airParticles", () => {
  it("la tavolozza di default non ha cuori; quella dell'easter egg ne ha un terzo", () => {
    expect(airParticles(120).some((p) => p.glyph === HEART)).toBe(false);
    const hearts = airParticles(120, 0, HEART_GLYPHS).filter((p) => p.glyph === HEART).length;
    expect(hearts).toBeGreaterThan(20);
    expect(hearts).toBeLessThan(60);
  });

  it("cambiare tavolozza non sposta le particelle: stesse posizioni e corse", () => {
    const plain = airParticles(120);
    const loving = airParticles(120, 0, HEART_GLYPHS);
    for (let i = 0; i < plain.length; i++) {
      expect(loving[i].left).toBe(plain[i].left);
      expect(loving[i].duration).toBe(plain[i].duration);
      expect(loving[i].delay).toBe(plain[i].delay);
    }
  });
});

describe("AsciiAtmosphere", () => {
  afterEach(cleanup);

  it("con hearts i cuori sono in pagina, in danger; senza, nessuno", () => {
    const { container } = render(<AsciiAtmosphere active hearts />);
    const hearts = [...container.querySelectorAll("span")].filter((s) => s.textContent === HEART);
    expect(hearts.length).toBeGreaterThan(0);
    for (const h of hearts) expect(h.className).toContain("air-heart");

    cleanup();
    const plain = render(<AsciiAtmosphere active />).container;
    expect([...plain.querySelectorAll("span")].some((s) => s.textContent === HEART)).toBe(false);
    expect(plain.querySelectorAll(".air-heart").length).toBe(0);
  });
});
```

- [ ] **Step 2: Eseguire il test e vederlo fallire**

Run: `cd frontend && npx vitest run tests/ascii-atmosphere.test.tsx`
Expected: FAIL, `HEART`/`HEART_GLYPHS` non esportati (`undefined`) e nessun cuore nel DOM.

- [ ] **Step 3: Implementare**

In `frontend/components/dashboard/ascii-atmosphere.tsx`:

Sostituire:

```tsx
/* Solo pulviscolo: `*` e `°` erano due glifi troppo grafici per un fondo. */
const GLYPHS = ["·", ".", "'", ","] as const;
```

con:

```tsx
/* Solo pulviscolo: `*` e `°` erano due glifi troppo grafici per un fondo. */
const GLYPHS = ["·", ".", "'", ","] as const;

/* L'easter egg (spec 2026-09-04): con la persona goodgirl un terzo del
   pulviscolo è fatto di cuori. Il cuore non sta in DM Mono e cade sul font di
   fallback — qui è accettabile, a differenza della cabina e della scritta:
   ogni particella è un elemento posizionato per conto suo, non una cella di
   una griglia, quindi la larghezza del glifo non sposta nulla. */
export const HEART = "♥";
export const HEART_GLYPHS = ["·", ".", HEART, "'", ",", HEART] as const;
```

Sostituire la firma di `airParticles`:

```tsx
export function airParticles(count: number, seed = 0): AirParticle[] {
```

con:

```tsx
export function airParticles(
  count: number, seed = 0, glyphs: readonly string[] = GLYPHS,
): AirParticle[] {
```

e nel corpo la riga `glyph: GLYPHS[Math.floor(hash01(i, seed + 6) * GLYPHS.length) % GLYPHS.length],` con:

```tsx
      glyph: glyphs[Math.floor(hash01(i, seed + 6) * glyphs.length) % glyphs.length],
```

Sostituire:

```tsx
const COUNT = 120;
const PARTICLES = airParticles(COUNT);
```

con:

```tsx
const COUNT = 120;
const PARTICLES = airParticles(COUNT);
/* Stesso seme: i cuori prendono il posto di alcune particelle, il campo non
   si ridistribuisce. */
const HEART_PARTICLES = airParticles(COUNT, 0, HEART_GLYPHS);
```

Sostituire la firma del componente e la prima riga:

```tsx
export function AsciiAtmosphere({ active }: { active: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
```

con:

```tsx
export function AsciiAtmosphere({ active, hearts = false }: {
  active: boolean;
  /** Cuori fra il pulviscolo: l'easter egg DJ GOODGIRL. */
  hearts?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const particles = hearts ? HEART_PARTICLES : PARTICLES;
```

e nel JSX sostituire:

```tsx
      {PARTICLES.map((p, i) => (
        <span key={i} className={p.near ? "air air-near" : "air"}
```

con:

```tsx
      {particles.map((p, i) => (
        <span key={i}
          className={`${p.near ? "air air-near" : "air"}${p.glyph === HEART ? " air-heart" : ""}`}
```

Aggiornare il JSDoc del componente aggiungendo, prima di `Decorativo e inerte al puntatore. */`: `Con \`hearts\` un terzo delle particelle è un cuore in danger.`

In `frontend/app/globals.css`, dopo la riga `.air-near { color: var(--c-fg); }` aggiungere:

```css
/* I cuori dell'easter egg DJ GOODGIRL: lo stesso rosso del colpo di cassa.
   Dopo `.air-near` di proposito, così vince anche sul piano vicino. */
.air-heart { color: var(--c-danger); }
```

- [ ] **Step 4: Eseguire il test e vederlo passare**

Run: `cd frontend && npx vitest run tests/ascii-atmosphere.test.tsx`
Expected: PASS, 3 test.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/ascii-atmosphere.tsx frontend/app/globals.css frontend/tests/ascii-atmosphere.test.tsx
git commit -m "feat(home): cuori nel pulviscolo con hearts, per l'easter egg"
```

---

### Task 5: La Home — l'interruttore e il cablaggio

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/tests/home-persona.test.tsx`

**Interfaces:**
- Consumes: `personaFor`, `Persona` da `@/lib/persona` (Task 1); `AsciiWordmark` `word`/`title` (Task 2); `AsciiDj` `figure` e `DjFigure` (Task 3); `AsciiAtmosphere` `hearts` (Task 4); `soundcloudStatus()` da `@/lib/api` (esiste già, riesportata da `lib/api.ts`).
- Produces: niente per altri task.

- [ ] **Step 1: Scrivere il test che fallisce**

`frontend/tests/home-persona.test.tsx`:
```tsx
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";
import { HEART } from "@/components/dashboard/ascii-atmosphere";

/* L'easter egg DJ GOODGIRL (spec 2026-09-04) si accende dalla Home leggendo
   l'username SoundCloud. Qui l'API è finta: conta che la persona arrivi ai
   tre componenti d'arte insieme, e che prima della risposta non ci sia
   niente da far lampeggiare. */

const soundcloudStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  apiGet: (path: string) => {
    if (path === "/api/stats") return Promise.resolve({ total_tracks: 10, with_local_file: 4 });
    return Promise.resolve([]);
  },
  getPipeline: () => Promise.resolve(null),
  listImportedPlaylists: () => Promise.resolve([]),
  soundcloudStatus: () => soundcloudStatus(),
}));

vi.mock("@/lib/player", () => ({
  usePlayer: () => ({ audible: false, play: vi.fn() }),
}));

vi.mock("@/lib/audio-analyser", () => ({
  primeOnFirstGesture: vi.fn(),
  readLevels: () => null,
  bandEdgeHz: () => 0,
}));

const status = (username: string | null) => ({ available: true, ytdlp_version: null, username });

const hasHearts = (root: HTMLElement) =>
  [...root.querySelectorAll("span")].some((s) => s.textContent === HEART);

describe("Home: la persona del frontespizio", () => {
  beforeEach(() => soundcloudStatus.mockReset());
  afterEach(cleanup);

  it("con xgiorgix dice DJ Goodgirl, la DJ è riccia e nell'aria ci sono cuori", async () => {
    soundcloudStatus.mockResolvedValue(status("xgiorgix"));
    const { container } = render(<Home />);
    // Niente lampeggio: finché la persona non è nota, la scritta non c'è.
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();

    expect(await screen.findByRole("heading", { level: 1, name: "DJ Goodgirl" })).toBeTruthy();
    await waitFor(() => expect(container.textContent).toContain("/(oo)\\"));
    expect(container.textContent).not.toContain("_(oo)_");
    expect(hasHearts(container)).toBe(true);
  });

  it("con un altro username resta Cratory, senza cuori", async () => {
    soundcloudStatus.mockResolvedValue(status("giorgia"));
    const { container } = render(<Home />);
    expect(await screen.findByRole("heading", { level: 1, name: "Cratory" })).toBeTruthy();
    await waitFor(() => expect(container.textContent).toContain("_(oo)_"));
    expect(container.textContent).not.toContain("/(oo)\\");
    expect(hasHearts(container)).toBe(false);
  });

  it("se lo stato SoundCloud non arriva, resta Cratory", async () => {
    soundcloudStatus.mockRejectedValue(new Error("backend giù"));
    render(<Home />);
    expect(await screen.findByRole("heading", { level: 1, name: "Cratory" })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Eseguire il test e vederlo fallire**

Run: `cd frontend && npx vitest run tests/home-persona.test.tsx`
Expected: FAIL. Il primo test cade su "niente lampeggio" (oggi l'h1 "Cratory" c'è subito) o su "DJ Goodgirl" mai trovato. Il terzo passa già (Cratory è il default): il denominatore è il primo.

- [ ] **Step 3: Cablare la Home**

In `frontend/app/page.tsx`:

Aggiornare l'import da `@/lib/api`:

```tsx
import {
  apiGet, getPipeline, listImportedPlaylists, soundcloudStatus,
  type LibraryStats, type SetlistSummary, type PipelineStatus, type Track, type Playlist,
} from "@/lib/api";
```

Aggiungere gli import (dopo `import { findTopPlaylist, pickRandom } from "@/lib/random-track";`):

```tsx
import { personaFor, type Persona } from "@/lib/persona";
```

e cambiare l'import della cabina in:

```tsx
import { AsciiDj, type DjFigure } from "@/components/dashboard/ascii-dj";
```

Prima di `export default function Home()` aggiungere:

```tsx
/* Il frontespizio per persona (spec 2026-09-04). `cratory` è la Home di
   sempre; `goodgirl` è l'easter egg per l'username SoundCloud xgiorgix: la
   scritta DJ GOODGIRL, la DJ riccia dietro la consolle, cuori nel pulviscolo.
   DJ GOODGIRL fa 65 colonne contro le 41 di CRATORY, quindi il corpo scende
   di un passo per stare nella stessa larghezza: 7px sul telefono (65 colonne
   sull'advance di DM Mono ≈ 273px, dentro i 309 disponibili) e 2.8cqw da lg
   (4.5 × 41 / 65). */
const FRONTISPIECE: Record<Persona, {
  word: string; title: string; sizeClass: string; figure: DjFigure; hearts: boolean;
}> = {
  cratory: {
    word: "CRATORY", title: "Cratory",
    sizeClass: "text-[12px] sm:text-lg md:text-xl lg:text-[min(4.1cqh,4.5cqw)]",
    figure: "boy", hearts: false,
  },
  goodgirl: {
    word: "DJ GOODGIRL", title: "DJ Goodgirl",
    sizeClass: "text-[7px] sm:text-sm md:text-lg lg:text-[min(4.1cqh,2.8cqw)]",
    figure: "girl", hearts: true,
  },
};
```

Dentro `Home`, dopo `const [error, setError] = useState<string | null>(null);` aggiungere:

```tsx
  /* `null` = persona non ancora nota: la scritta aspetta, così l'ingresso dal
     rumore si risolve direttamente nella parola giusta invece di mostrare
     CRATORY e poi cambiarlo. In locale la risposta arriva in pochi ms. */
  const [persona, setPersona] = useState<Persona | null>(null);
```

Nell'`useEffect` di montaggio, dopo la riga `listImportedPlaylists().then(setPlaylists).catch(() => setPlaylists([]));` aggiungere:

```tsx
    // L'easter egg: la persona del frontespizio dipende dall'username SoundCloud.
    soundcloudStatus().then((s) => setPersona(personaFor(s.username))).catch(() => setPersona("cratory"));
```

Dopo `const empty = stats != null && stats.total_tracks === 0;` aggiungere:

```tsx
  const front = persona ? FRONTISPIECE[persona] : null;
```

Nel JSX sostituire:

```tsx
        <AsciiAtmosphere active={player.audible} />
```

con:

```tsx
        <AsciiAtmosphere active={player.audible} hearts={front?.hearts ?? false} />
```

sostituire:

```tsx
          <div className="flex-none">
            <AsciiWordmark sizeClass="text-[12px] sm:text-lg md:text-xl lg:text-[min(4.1cqh,4.5cqw)]" />
          </div>
```

con:

```tsx
          <div className="flex-none">
            {front && <AsciiWordmark word={front.word} title={front.title} sizeClass={front.sizeClass} />}
          </div>
```

e nella cabina sostituire:

```tsx
                <AsciiDj
                  animate={player.audible}
```

con:

```tsx
                <AsciiDj
                  figure={front?.figure ?? "boy"}
                  animate={player.audible}
```

- [ ] **Step 4: Eseguire il test e vederlo passare**

Run: `cd frontend && npx vitest run tests/home-persona.test.tsx`
Expected: PASS, 3 test.

- [ ] **Step 5: Tutta la suite, lint e tipi**

Run: `cd frontend && npm run test:unit && npm run lint && npx tsc --noEmit`
Expected: tutti i test PASS, lint senza errori, tsc senza errori.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/page.tsx frontend/tests/home-persona.test.tsx
git commit -m "feat(home): easter egg DJ GOODGIRL per l'username SoundCloud xgiorgix"
```

---

### Task 6: Verifica in preview e diario

**Files:**
- Modify: `PROGRESS.md` (nuova voce in testa a "Current state by area")
- Eventuale ritocco: `frontend/app/page.tsx` (solo il `sizeClass` di `goodgirl`, se in preview la scritta scrolla o resta piccola)

**Interfaces:** niente.

- [ ] **Step 1: Backend e frontend in preview**

Il backend serve solo per `GET /api/soundcloud/status`: qualunque backend Cratory su `:8000` va bene. Verificare se ce n'è già uno:

```bash
curl -s http://127.0.0.1:8000/api/soundcloud/status
```

Se non risponde, avviarlo dal worktree col venv del checkout principale (il worktree non ha `.venv`):

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/uvicorn app.main:app --port 8000
```

(in background, con il tool Bash `run_in_background`; non è un server di preview del pannello). Poi il frontend del worktree con `preview_start` sulla configurazione di `.claude/launch.json` del worktree (leggerlo prima: se punta alla porta `3000` e quella è occupata dal dev server del checkout principale, cambiare temporaneamente porta e ripristinare il file prima del commit — è tracciato in git).

- [ ] **Step 2: Salvare l'username attuale e impostare xgiorgix**

```bash
curl -s http://127.0.0.1:8000/api/soundcloud/status
```

Annotare il campo `username` (può essere `null`). Poi:

```bash
curl -s -X PUT http://127.0.0.1:8000/api/soundcloud/config -H 'content-type: application/json' -d '{"username":"xgiorgix"}'
```

- [ ] **Step 3: Guardare la Home**

Aprire `/` nel pannello. Verificare con `read_page`/`get_page_text` e uno screenshot: la scritta DJ GOODGIRL risolta senza barra di scorrimento nella cornice, la DJ riccia (`()()`, `/(oo)\`, `//\  ///`), nessun errore in console. Con `resize_window` preset `mobile` controllare che la scritta stia nei 375px senza scroll orizzontale; tornare a `desktop`. Se la scritta eccede o resta troppo piccola, ritoccare solo il `sizeClass` di `goodgirl` in `FRONTISPIECE` e ricontrollare.

Per i cuori: premere la cabina (suona una traccia a caso dalla libreria posseduta) e verificare che nel pulviscolo compaiano `♥` in rosso; con `get_page_text` o `javascript_tool` contare `document.querySelectorAll(".air-heart").length` (atteso: fra 20 e 60).

- [ ] **Step 4: Ripristinare l'username**

Se il valore annotato era una stringa:

```bash
curl -s -X PUT http://127.0.0.1:8000/api/soundcloud/config -H 'content-type: application/json' -d '{"username":"<valore annotato>"}'
```

Se era `null` non c'è un endpoint per cancellarlo: dirlo esplicitamente all'utente nel messaggio finale (l'username resta `xgiorgix` e lo può cambiare da Impostazioni). Ricaricare la Home e verificare che sia tornata CRATORY (o resti DJ GOODGIRL se il valore non è ripristinabile, dicendolo).

- [ ] **Step 5: Ripristinare i file di lavoro**

```bash
git status --porcelain
```

Expected: solo i file del task (PROGRESS.md e, se ritoccato, page.tsx). Se compaiono `.claude/launch.json` o `frontend/tsconfig.json` sporcati dal dev server, `git checkout -- <file>`.

- [ ] **Step 6: La voce nel diario**

In `PROGRESS.md`, subito sotto `## Current state by area`, aggiungere come prima voce:

```markdown
- **DJ GOODGIRL, un easter egg sul frontespizio** (2026-09-04): con l'username
  SoundCloud `xgiorgix` la Home cambia persona — la scritta che si risolve dal
  rumore dice DJ GOODGIRL, la DJ dietro la consolle è una ragazza riccia
  (`()()`, `/(oo)\`, scollo a V) e un terzo del pulviscolo che sale con la
  musica è fatto di cuori nel rosso della cassa. Tutto frontend, tutto a
  prop con default: `AsciiWordmark` prende `word`/`title` (alfabeto esteso a
  D J G I L e spazio), `AsciiDj` prende `figure`, `AsciiAtmosphere` prende
  `hearts`; la decisione sta in `lib/persona.ts`. La scritta aspetta la
  risposta di `/api/soundcloud/status` prima di montarsi, così l'ingresso si
  risolve direttamente nella parola giusta. Spec in
  `docs/superpowers/specs/2026-09-04-dj-goodgirl-easter-egg-design.md`.
```

- [ ] **Step 7: Commit**

```bash
git add PROGRESS.md frontend/app/page.tsx
git commit -m "docs: diario dell'easter egg DJ GOODGIRL"
```

(se `page.tsx` non è cambiato, `git add` lo ignora senza errori).
