"use client";

import { useEffect, useState } from "react";

/* Il DJ in ascii della dashboard. Due strati:
   - un core puro e deterministico, `djFrame(tick)`, che produce il fotogramma
     come righe di larghezza fissa (testato su dimensioni, fasi, determinismo);
   - un guscio React che avanza il tick ogni ~500ms e resta fermo con
     `prefers-reduced-motion`.
   L'arte NON è pinnata dai test: si può raffinare liberamente, purché le
   righe restino a larghezza costante (fit() la garantisce comunque). */

export const DJ_COLS = 52;
export const DJ_AIR_ROWS = 4;

const SPIN = ["|", "/", "-", "\\"] as const;
/* Solo glifi presenti in DM Mono: le note musicali unicode (♪ ♫) cadono sul
   font di fallback con larghezza diversa e disallineano le colonne. */
const NOTES = ["°", "*", "·"] as const;

/* Testa (5 righe) + collo + spalle. La testa "annuisce": in battere scende di
   una riga e il collo scompare dietro il colletto; in levare risale e il collo
   si vede. Altezza totale del corpo costante: 5 (testa) + 1 (finestra del
   bob) + 2 (spalle) = 8 righe. EYES e MOUTH sono token a lunghezza fissa. */
const HEAD_TEMPLATE = [
  "                     .-------.                      ",
  "                  .-'  .---.  '-.                   ",
  "                 ((   ( EYES )   ))                 ",
  "                  ||   \\ MOUTH/   ||                ",
  "                   '-.__'---'__.-'                  ",
];
const NECK_ROW = "                      |     |                       ";
const SHOULDER_ROWS = [
  "                  .--'       '--.                   ",
  "               __/               \\__                ",
];
const BODY_ROWS = HEAD_TEMPLATE.length + 1 + SHOULDER_ROWS.length;

/* Console: composta programmaticamente (bordi, piatti, EQ, fader, BPM) così
   l'allineamento del bordo destro non dipende da conteggi manuali. */
const INNER = DJ_COLS - 8;          // larghezza utile dentro "  |...|  "
const SIDE = 13;                    // celle piatto, sinistra e destra
const CENTER = INNER - SIDE * 2;    // cella centrale (EQ / fader): 18
const EQ_BARS = 9;
const CONSOLE_ROWS = 6;

export const DJ_ROWS = DJ_AIR_ROWS + BODY_ROWS + CONSOLE_ROWS;
/* Riga assoluta e colonne della fila alta dell'EQ: servono al guscio per
   colorare i picchi in danger (la grammatica decorativa dei DJ loader). */
export const DJ_EQ_TOP_ROW = DJ_AIR_ROWS + BODY_ROWS + 1;
// Prefisso di riga "  |" = 3 colonne, poi la cella sinistra e il padding
// che centra le barre nella cella centrale.
export const DJ_EQ_COL_START = 3 + SIDE + Math.floor((CENTER - EQ_BARS) / 2);
export const DJ_EQ_COL_END = DJ_EQ_COL_START + EQ_BARS;

/* LCG minimale: pseudo-casualità deterministica dal seme, mai Math.random.
   Due giri di riscaldamento: con semi vicini (tick consecutivi) il primo
   output è correlato. */
function lcg(seed: number): () => number {
  let s = (seed ^ 0x9e3779b9) >>> 0;
  const next = () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
  next();
  next();
  return next;
}

function fit(line: string): string {
  return line.length > DJ_COLS ? line.slice(0, DJ_COLS) : line.padEnd(DJ_COLS);
}

function centerIn(s: string, width: number): string {
  const pad = Math.max(0, width - s.length);
  const left = Math.floor(pad / 2);
  return " ".repeat(left) + s + " ".repeat(pad - left);
}

function consoleRow(left: string, center: string, right: string): string {
  const inner = left.padEnd(SIDE) + centerIn(center, CENTER) + right.padStart(SIDE);
  return `  |${inner}|  `;
}

/** Fotogramma al tick dato: DJ_ROWS righe larghe DJ_COLS. Deterministica. */
export function djFrame(tick: number): string[] {
  /* Aria: note spawnate ogni 2 tick che salgono di una riga a tick, derivando
     di ±1 colonna per passo, e svaniscono uscendo dall'alto. */
  const air: string[] = [];
  for (let row = 0; row < DJ_AIR_ROWS; row++) air.push(" ".repeat(DJ_COLS));
  for (let age = 0; age < DJ_AIR_ROWS; age++) {
    const born = tick - age;
    if (born < 0 || born % 2 !== 0) continue;
    const r = lcg(born);
    let col = 6 + Math.floor(r() * (DJ_COLS - 12));
    for (let step = 0; step < age; step++) col += Math.floor(r() * 3) - 1;
    col = Math.min(DJ_COLS - 2, Math.max(1, col));
    const glyph = NOTES[(born / 2) % NOTES.length];
    const row = DJ_AIR_ROWS - 1 - age;
    air[row] = air[row].slice(0, col) + glyph + air[row].slice(col + 1);
  }

  /* Corpo: blink ogni 7 tick, bocca che "canta" ogni 8, nodding sul battere. */
  const blink = tick % 7 === 6;
  const sing = tick % 8 === 3;
  const head = HEAD_TEMPLATE.map((line) =>
    line.replace("EYES", blink ? "-   -" : "o   o").replace("MOUTH", sing ? " o  " : " -  "),
  );
  const down = Math.floor(tick / 2) % 2 === 1;
  const body = [...(down ? ["", ...head] : [...head, NECK_ROW]), ...SHOULDER_ROWS];

  /* Console: piatti sfalsati, EQ 9 barre a 3 altezze, fader triangolare,
     display BPM che cambia lentamente. */
  const spinL = SPIN[tick % 4];
  const spinR = SPIN[(tick + 2) % 4];
  const heights: number[] = [];
  for (let i = 0; i < EQ_BARS; i++) heights.push(Math.floor(lcg(tick * 131 + i * 17)() * 4));
  const eqTop = heights.map((h) => (h === 3 ? "|" : " ")).join("");
  const eqMid = heights.map((h) => (h >= 2 ? "|" : " ")).join("");
  const eqBot = heights.map((h) => (h >= 1 ? "|" : ".")).join("");
  const m = tick % 20;
  const p = m <= 10 ? m : 20 - m;
  const fader = `[${"=".repeat(p)}o${"=".repeat(10 - p)}]`;
  const bpm = String(124 + ((Math.floor(tick / 8) * 3) % 9)).padStart(3);
  const rec = tick % 4 < 2 ? "• REC" : "  REC";

  /* Le celle laterali condividono le colonne: scatola del piatto (8 char) e
     parentesi del piatto allineate sugli stessi bordi. */
  const deck = [
    "  ." + "_".repeat(INNER) + ".  ",
    consoleRow("   .------.", eqTop, ".------.   "),
    consoleRow(`   (  ${spinL}   )`, eqMid, `(  ${spinR}   )   `),
    consoleRow("   '------'", eqBot, "'------'   "),
    consoleRow(`   ${bpm} BPM`, fader, `${rec}   `),
    "  '" + "_".repeat(INNER) + "'  ",
  ];

  return [...air, ...body, ...deck].map(fit);
}

function usePrefersReducedMotion(): boolean {
  // Lettura iniziale nel lazy initializer (niente setState sincrono in effect);
  // la guardia su window copre il prerender server di Next.
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined"
      && typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/* La fila alta dell'EQ, colorata carattere per carattere: le barre a piena
   altezza sono i "picchi" e prendono danger, come il notch dell'Equalizer. */
function EqTopRow({ line }: { line: string }) {
  const pre = line.slice(0, DJ_EQ_COL_START);
  const eq = line.slice(DJ_EQ_COL_START, DJ_EQ_COL_END);
  const post = line.slice(DJ_EQ_COL_END);
  return (
    <pre className="leading-[1.15]">
      {pre}
      {eq.split("").map((ch, i) => (
        <span key={i} className={ch === "|" ? "text-danger" : undefined}>{ch}</span>
      ))}
      {post}
    </pre>
  );
}

/** Il DJ animato della dashboard: puramente decorativo (aria-hidden). */
export function AsciiDj() {
  const reduced = usePrefersReducedMotion();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setTick((t) => (t + 1) % 100000), 500);
    return () => clearInterval(id);
  }, [reduced]);

  const lines = djFrame(reduced ? 0 : tick);
  const bodyEnd = DJ_AIR_ROWS + BODY_ROWS;
  const air = lines.slice(0, DJ_AIR_ROWS);
  const body = lines.slice(DJ_AIR_ROWS, bodyEnd);
  const consoleTop = lines.slice(bodyEnd, DJ_EQ_TOP_ROW);
  const eqRow = lines[DJ_EQ_TOP_ROW];
  const rest = lines.slice(DJ_EQ_TOP_ROW + 1);

  return (
    <div aria-hidden="true" className="select-none text-[9px] sm:text-xs">
      <div className="text-faint">
        {air.map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
      </div>
      <div className="text-muted">
        {body.map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
      </div>
      <div className="text-fg">
        {consoleTop.map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
        <EqTopRow line={eqRow} />
        {rest.map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
      </div>
    </div>
  );
}
