"use client";

import { useEffect, useState } from "react";

/* La cabina del DJ in ascii (arte fornita dall'utente): due casse, il DJ coi
   capelli al vento dietro la console in prospettiva. Due strati:
   - un core puro e deterministico, `djFrame(tick)`, che produce il fotogramma
     come righe di larghezza fissa (testato su dimensioni, fasi, determinismo);
   - un guscio React che avanza il tick ogni ~500ms, resta fermo con
     `prefers-reduced-motion` e, se gli si passa `onActivate`, diventa un
     bottone (la dashboard ci attacca "suona una traccia a caso").
   Le parti animate sono localizzate con indexOf sul template: niente
   coordinate a mano, e ogni sostituzione ha la lunghezza del pezzo che
   rimpiazza, così l'allineamento non può rompersi. */

const SCENE = [
  " #########\\                                                      #########\\",
  " #(=====)# |                           ///                       #(=====)# |",
  " ######### |                         _(oo)_                      ######### |",
  " #-------# |                        //    //                     #-------# |",
  " #|  -  |# |          -- __________//____//__________--          #|  -  |# |",
  " #|( O )|# |    --  --  /-/\\-  -+/ -+- -+- /-/\\-  -+/| --  --    #|( O )|# |",
  " #|  -  |# |  --  --   / /( o ) / ^^^ /// / /( o ) / /   --  --  #|  -  |# |",
  " #|-----|# |--        / &   - o/ ^^^ /// / &   - o/ /          --#|-----|# |",
  " #########/          |#########|#########|########|/             #########/",
];

export const DJ_AIR_ROWS = 3;
export const DJ_COLS = Math.max(...SCENE.map((l) => l.length));
export const DJ_ROWS = DJ_AIR_ROWS + SCENE.length;
/* Riga assoluta dei woofer: il guscio colora la 'O' del colpo di cassa in
   danger, citando la grammatica decorativa dei DJ loader (Equalizer/EqMeter). */
export const DJ_WOOFER_ROW = DJ_AIR_ROWS + 5;

const SPIN = ["|", "/", "-", "\\"] as const;
/* Solo glifi presenti in DM Mono: le note musicali unicode (♪ ♫) cadono sul
   font di fallback con larghezza diversa e disallineano le colonne. */
const NOTES = ["°", "*", "·"] as const;
const WAVES = ["^^^", "~^~", "^~^"] as const;

/* Le posizioni delle parti animate, trovate una volta sola sul template. */
const AT = {
  hair: SCENE[1].indexOf("///"),
  tweetL: SCENE[1].indexOf("(=====)"),
  tweetR: SCENE[1].lastIndexOf("(=====)"),
  face: SCENE[2].indexOf("(oo)"),
  woofL: SCENE[5].indexOf("( O )"),
  woofR: SCENE[5].lastIndexOf("( O )"),
  platL: SCENE[6].indexOf("( o )"),
  platR: SCENE[6].lastIndexOf("( o )"),
  wave1: SCENE[6].indexOf("^^^"),
  slash1: SCENE[6].indexOf("///"),
  wave2: SCENE[7].indexOf("^^^"),
  slash2: SCENE[7].indexOf("///"),
};

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

function splice(line: string, col: number, s: string): string {
  if (col < 0) return line;
  return line.slice(0, col) + s + line.slice(col + s.length);
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
    air[row] = splice(air[row], col, glyph);
  }

  const thump = tick % 2 === 0;              // il colpo di cassa
  const blink = tick % 7 === 6;
  const wink = tick % 23 === 11;
  const scene = SCENE.slice();

  scene[1] = splice(scene[1], AT.hair, tick % 4 < 2 ? "///" : "\\\\\\");
  scene[1] = splice(scene[1], AT.tweetL, thump ? "(-=-=-)" : "(=====)");
  scene[1] = splice(scene[1], AT.tweetR, thump ? "(-=-=-)" : "(=====)");
  scene[2] = splice(scene[2], AT.face, blink ? "(--)" : wink ? "(o-)" : "(oo)");
  scene[5] = splice(scene[5], AT.woofL, thump ? "( O )" : "( o )");
  scene[5] = splice(scene[5], AT.woofR, thump ? "( O )" : "( o )");
  scene[6] = splice(scene[6], AT.platL, `( ${SPIN[tick % 4]} )`);
  scene[6] = splice(scene[6], AT.platR, `( ${SPIN[(tick + 2) % 4]} )`);
  scene[6] = splice(scene[6], AT.wave1, WAVES[tick % 3]);
  scene[7] = splice(scene[7], AT.wave2, WAVES[(tick + 1) % 3]);
  scene[6] = splice(scene[6], AT.slash1, thump ? "///" : "\\\\\\");
  scene[7] = splice(scene[7], AT.slash2, thump ? "\\\\\\" : "///");

  return [...air, ...scene].map(fit);
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

/* La riga dei woofer: sul colpo di cassa la 'O' grande prende danger. */
function WooferRow({ line }: { line: string }) {
  return (
    <pre className="leading-[1.15]">
      {line.split("").map((ch, i) => (
        <span key={i} className={ch === "O" ? "text-danger" : undefined}>{ch}</span>
      ))}
    </pre>
  );
}

/** La cabina animata. Con `onActivate` diventa un bottone (etichetta `label`,
 *  suggerimento visibile `hint` sotto la scena). `animate` è il rubinetto: la
 *  dashboard lo lega al suono che esce davvero dal player, così la consolle si
 *  muove solo mentre c'è musica. A rubinetto chiuso la scena resta dov'era —
 *  come un fermo immagine, non un ritorno a capo. */
export function AsciiDj({ onActivate, label, hint, animate = true }: {
  onActivate?: () => void;
  label?: string;
  hint?: string;
  animate?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const [tick, setTick] = useState(0);
  const running = animate && !reduced;
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick((t) => (t + 1) % 100000), 500);
    return () => clearInterval(id);
  }, [running]);

  const lines = djFrame(reduced ? 0 : tick);

  const art = (
    <div aria-hidden="true" className="select-none text-[9px] sm:text-sm md:text-base lg:text-lg xl:text-xl 2xl:text-2xl">
      <div className="text-faint">
        {lines.slice(0, DJ_AIR_ROWS).map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
      </div>
      <div className="text-fg">
        {lines.slice(DJ_AIR_ROWS, DJ_WOOFER_ROW).map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
        <WooferRow line={lines[DJ_WOOFER_ROW]} />
        {lines.slice(DJ_WOOFER_ROW + 1).map((l, i) => <pre key={i} className="leading-[1.15]">{l}</pre>)}
      </div>
    </div>
  );

  if (!onActivate) return art;
  return (
    <button
      type="button"
      onClick={onActivate}
      aria-label={label}
      className="group block cursor-pointer focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg"
    >
      {art}
      {hint && (
        <div className="mt-3 text-center text-[10px] uppercase tracking-wider text-faint transition-colors group-hover:text-muted">
          {hint}
        </div>
      )}
    </button>
  );
}
