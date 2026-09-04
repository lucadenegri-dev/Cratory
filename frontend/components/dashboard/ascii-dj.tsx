"use client";

import { useEffect, useRef, useState } from "react";
import { readLevels } from "@/lib/audio-analyser";
import { resolveLines } from "@/lib/ascii-resolve";
import { useAsciiIntro } from "@/lib/use-ascii-intro";

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

export const DJ_AIR_ROWS = 3;
export const DJ_COLS = Math.max(...SCENE.map((l) => l.length));
export const DJ_ROWS = DJ_AIR_ROWS + SCENE.length;
/* Riga assoluta dei woofer: il guscio colora la 'O' del colpo di cassa in
   danger, citando la grammatica decorativa dei DJ loader (Equalizer/EqMeter). */
export const DJ_WOOFER_ROW = DJ_AIR_ROWS + 5;

/* Il tick su cui la cabina sta ferma quando non suona nulla. Dispari di
   proposito: il colpo di cassa cade sui tick pari (`thump`), quindi lo zero
   mostrerebbe tweeter compressi e la 'O' grande in rosso — la posa di un colpo
   mentre non esce alcun suono. Da quando la cabina apre la Home, subito sotto
   il frontespizio, è la prima cosa che si guarda e l'incoerenza si nota.
   L'aria non si svuota su nessun tick (le note nascono sui pari e ne resta
   sempre almeno una viva), ma un glifo che fluttua non stona: stonava la
   cassa. */
export const DJ_REST_TICK = 1;

const SPIN = ["|", "/", "-", "\\"] as const;
/* Solo glifi presenti in DM Mono: le note musicali unicode (♪ ♫) cadono sul
   font di fallback con larghezza diversa e disallineano le colonne.
   Un solo glifo, il punto medio: `*` e `°` erano troppo grafici accanto al
   pulviscolo di sfondo, che è fatto della stessa materia. */
const NOTES = ["·"] as const;
const WAVES = ["^^^", "~^~", "^~^"] as const;

/* Le posizioni delle parti animate, trovate una volta sola per template.
   I capelli non ci sono: restano quelli del template, fermi. */
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

/** Fotogramma al tick dato: DJ_ROWS righe larghe DJ_COLS. Deterministica.
 *
 *  `tick` muove l'aria; `sceneTick` (default: `tick`) muove la cabina. Sono
 *  separati perché la Home fa respirare l'aria anche a musica ferma, con la
 *  consolle immobile. `thump` sovrascrive il colpo di cassa: quando c'è
 *  l'analisi dell'audio la cassa batte sui bassi veri della traccia, non su un
 *  contatore. `figure` sceglie chi sta dietro la consolle (default `boy`;
 *  `girl` è l'easter egg DJ GOODGIRL). */
export function djFrame(
  tick: number,
  opts?: { sceneTick?: number; thump?: boolean; figure?: DjFigure },
): string[] {
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

  const sceneTick = opts?.sceneTick ?? tick;
  const thump = opts?.thump ?? sceneTick % 2 === 0;   // il colpo di cassa
  const blink = sceneTick % 7 === 6;
  const wink = sceneTick % 23 === 11;
  const { scene: base, at: AT } = FIGURES[opts?.figure ?? "boy"];
  const scene = base.slice();

  scene[1] = splice(scene[1], AT.tweetL, thump ? "(-=-=-)" : "(=====)");
  scene[1] = splice(scene[1], AT.tweetR, thump ? "(-=-=-)" : "(=====)");
  scene[2] = splice(scene[2], AT.face, blink ? "(--)" : wink ? "(o-)" : "(oo)");
  scene[5] = splice(scene[5], AT.woofL, thump ? "( O )" : "( o )");
  scene[5] = splice(scene[5], AT.woofR, thump ? "( O )" : "( o )");
  scene[6] = splice(scene[6], AT.platL, `( ${SPIN[sceneTick % 4]} )`);
  scene[6] = splice(scene[6], AT.platR, `( ${SPIN[(sceneTick + 2) % 4]} )`);
  scene[6] = splice(scene[6], AT.wave1, WAVES[sceneTick % 3]);
  scene[7] = splice(scene[7], AT.wave2, WAVES[(sceneTick + 1) % 3]);
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

/* Il colpo di cassa preso dall'audio vero (lib/audio-analyser.ts).
 *  Ritorna `null` quando non c'è analisi da usare — Web Audio assente, oppure
 *  sorgente cross-origin che restituisce zeri (le preview di terzi): in quel
 *  caso la cabina torna al suo contatore, invece di restare immobile mentre
 *  qualcosa sta suonando. Mezzo secondo di silenzio pieno basta a dichiararlo:
 *  una pausa vera fra due battute non arriva a tanto. */
const SILENT_FRAMES = 30;

function useAudioThump(active: boolean): boolean | null {
  const [thump, setThump] = useState<boolean | null>(null);
  const raf = useRef(0);

  useEffect(() => {
    if (!active) return;
    let env = 0;             // inviluppo lento dei bassi: la soglia si adatta
    let silent = 0;
    let last: boolean | null = null;
    const publish = (v: boolean | null) => { if (v !== last) { last = v; setThump(v); } };
    const step = () => {
      const levels = readLevels(1);
      if (!levels) {
        publish(null);
      } else if (levels.bass <= 0 && levels.mid <= 0) {
        silent += 1;
        if (silent >= SILENT_FRAMES) publish(null);
      } else {
        silent = 0;
        env += (levels.bass - env) * 0.06;
        publish(levels.bass > env * 1.12 + 0.04);
      }
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [active]);

  // Derivato invece che azzerato in un effect: spegnendo `active` il valore
  // reso torna nullo senza un setState sincrono.
  return active ? thump : null;
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

/** La cabina animata. Con `onActivate` diventa un bottone: l'etichetta `label`
 *  esiste solo per gli assistivi, la scena non porta scritte. `animate` è il rubinetto: la
 *  dashboard lo lega al suono che esce davvero dal player, così la consolle si
 *  muove solo mentre c'è musica. A rubinetto chiuso la scena resta dov'era —
 *  come un fermo immagine, non un ritorno a capo. */
export function AsciiDj({ onActivate, label, animate = true, sizeClass, figure = "boy" }: {
  onActivate?: () => void;
  label?: string;
  animate?: boolean;
  /** Chi sta dietro la consolle: `girl` è l'easter egg DJ GOODGIRL. */
  figure?: DjFigure;
  /** Corpo del carattere dell'arte. Il default è la scala per breakpoint; la
   *  Home passa una misura in unità di container per riempire la schermata. */
  sizeClass?: string;
}) {
  const reduced = usePrefersReducedMotion();
  const [tick, setTick] = useState(DJ_REST_TICK);
  const [air, setAir] = useState(DJ_REST_TICK);
  const running = animate && !reduced;
  const intro = useAsciiIntro();
  const audioThump = useAudioThump(running);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick((t) => (t + 1) % 100000), 500);
    return () => clearInterval(id);
  }, [running]);

  // L'aria ha una cadenza sua, più lenta della consolle, ma lo stesso
  // rubinetto: a musica ferma non si muove niente in pagina.
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setAir((a) => (a + 1) % 100000), 420);
    return () => clearInterval(id);
  }, [running]);

  /* A rubinetto chiuso la posa resta quella dove si era fermata (i piatti non
     tornano a capo), ma il colpo di cassa si rilassa: un woofer rosso acceso
     mentre non esce alcun suono è la stessa incoerenza per cui DJ_REST_TICK è
     dispari. Con l'analisi viva il colpo lo detta l'audio; senza, il contatore. */
  const lines = resolveLines(
    djFrame(reduced ? DJ_REST_TICK : air, {
      figure,
      sceneTick: reduced ? DJ_REST_TICK : tick,
      ...(!running ? { thump: false } : audioThump === null ? {} : { thump: audioThump }),
    }),
    intro,
  );

  /* La scala sale per breakpoint ma di un passo più bassa di quanto sarebbe
     naturale in alto: la Home deve stare in una schermata senza scrollare, e
     con 12 righe la scena è l'elemento da cui si recupera più altezza. */
  const art = (
    <div aria-hidden="true"
      className={`select-none ${sizeClass ?? "text-[9px] sm:text-sm md:text-base lg:text-base xl:text-lg 2xl:text-xl"}`}>
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
    </button>
  );
}
