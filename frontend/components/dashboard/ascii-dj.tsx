"use client";

import { useEffect, useState } from "react";

/* Il DJ in ascii della dashboard. Due strati:
   - un core puro e deterministico, `djFrame(tick)`, che produce il fotogramma
     come righe di larghezza fissa (testato su dimensioni, fasi, determinismo);
   - un guscio React che avanza il tick ogni ~500ms e resta fermo con
     `prefers-reduced-motion`.
   L'arte è volutamente NON pinnata dai test: si può raffinare liberamente,
   purché le sostituzioni dinamiche restino a lunghezza costante. */

export const DJ_COLS = 38;
export const DJ_AIR_ROWS = 3;

const SPIN = ["|", "/", "-", "\\"] as const;
const NOTES = ["\u266a", "\u266b", "\u00b7"] as const; // ♪ ♫ ·

/* Template della scena (righe sotto l'aria). I token a lunghezza fissa vengono
   sostituiti a ogni tick: EYES (occhi), SPINL/SPINR (piatti), UPPEREQ/LOWEREQ
   (barre del mixer), XFADERXFA (crossfader). Ogni riga viene normalizzata a
   DJ_COLS, quindi un errore di conteggio qui non rompe mai il layout. */
const BODY_TEMPLATE = [
  "               _______                ",
  "            .-'  ___  '-.             ",
  "          ((   ( EYES )   ))          ",
  "           ||   \\ '-' /   ||          ",
  "            \\_.-'-----'-._/           ",
  "           .-'|         |'-.          ",
  "        __/   '_________'   \\__       ",
];
const CONSOLE_TEMPLATE = [
  " .________________________________.   ",
  " |  .----.     UPPEREQ     .----. |   ",
  " | ( SPINL )   LOWEREQ    ( SPINR )   ",
  " |  '----'   [XFADERXFA]   '----' |   ",
  " '--------------------------------'   ",
];

export const DJ_ROWS = DJ_AIR_ROWS + BODY_TEMPLATE.length + CONSOLE_TEMPLATE.length;

/* Riga assoluta e colonne della fila alta dell'EQ: servono al guscio per
   colorare i picchi in danger (la grammatica decorativa dei DJ loader). */
export const DJ_EQ_TOP_ROW = DJ_AIR_ROWS + BODY_TEMPLATE.length + 1;
export const DJ_EQ_COL_START = CONSOLE_TEMPLATE[1].indexOf("UPPEREQ");
export const DJ_EQ_COL_END = DJ_EQ_COL_START + 7;

/* LCG minimale: pseudo-casualità deterministica dal seme, mai Math.random.
   Due giri di riscaldamento: con semi vicini (tick consecutivi) il primo
   output è correlato e l'EQ risulterebbe piatto. */
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

/** Fotogramma al tick dato: DJ_ROWS righe larghe DJ_COLS. Deterministica. */
export function djFrame(tick: number): string[] {
  /* Aria: note spawmate ogni 2 tick che salgono di una riga a tick e
     svaniscono uscendo dall'alto. Colonna e glifo dal LCG del tick di spawn. */
  const air: string[] = [];
  for (let row = 0; row < DJ_AIR_ROWS; row++) air.push(" ".repeat(DJ_COLS));
  for (let age = 0; age < DJ_AIR_ROWS; age++) {
    const born = tick - age;
    if (born < 0 || born % 2 !== 0) continue;
    const r = lcg(born);
    const col = 5 + Math.floor(r() * (DJ_COLS - 10));
    // Glifo ciclico sull'indice di spawn: varietà garantita, niente streak.
    const glyph = NOTES[(born / 2) % NOTES.length];
    const row = DJ_AIR_ROWS - 1 - age;
    air[row] = air[row].slice(0, col) + glyph + air[row].slice(col + 1);
  }

  /* Corpo: gli occhi sbattono un tick ogni 7 (~3.5s a 500ms). */
  const blink = tick % 7 === 6;
  const body = BODY_TEMPLATE.map((line) => line.replace("EYES", blink ? "-  -" : "o  o"));

  /* Console: piatti in fase sfalsata, EQ pseudo-casuale su due file,
     crossfader a onda triangolare. */
  const spinL = SPIN[tick % 4];
  const spinR = SPIN[(tick + 2) % 4];
  let upper = "";
  let lower = "";
  for (let i = 0; i < 7; i++) {
    const h = Math.floor(lcg(tick * 31 + i * 7)() * 3);
    upper += h === 2 ? "|" : " ";
    lower += h >= 1 ? "|" : ".";
  }
  const m = tick % 16;
  const p = m <= 8 ? m : 16 - m;
  const fader = "=".repeat(p) + "o" + "=".repeat(8 - p);
  // Ogni sostituzione ha la stessa lunghezza del token: l'allineamento regge.
  const deck = CONSOLE_TEMPLATE.map((line) =>
    line
      .replace("SPINL", `  ${spinL}  `)
      .replace("SPINR", `  ${spinR}  `)
      .replace("UPPEREQ", upper)
      .replace("LOWEREQ", lower)
      .replace("XFADERXFA", fader),
  );

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
  const bodyEnd = DJ_AIR_ROWS + BODY_TEMPLATE.length;
  const air = lines.slice(0, DJ_AIR_ROWS);
  const body = lines.slice(DJ_AIR_ROWS, bodyEnd);
  const consoleTop = lines.slice(bodyEnd, DJ_EQ_TOP_ROW);
  const eqRow = lines[DJ_EQ_TOP_ROW];
  const rest = lines.slice(DJ_EQ_TOP_ROW + 1);

  return (
    <div aria-hidden="true" className="select-none text-[11px]">
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
