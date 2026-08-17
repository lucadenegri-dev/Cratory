"use client";

/* Analisi in tempo reale di quello che esce davvero dal player, per la cabina
   della Home: i woofer battono sui bassi veri della traccia, lo spettro sotto
   la console è il suo contenuto in frequenza.
 *
 * Regola non negoziabile: NIENTE di qui dentro può azzittire la riproduzione.
 * `createMediaElementSource` è irreversibile e dirotta l'uscita dell'elemento
 * dentro il grafo — se il contesto è sospeso (politica di autoplay) l'audio
 * sparisce. Quindi l'elemento si tocca solo a contesto già `running`, e il
 * contesto si crea/riprende su un gesto reale dell'utente
 * (`primeOnFirstGesture`). Ogni errore lascia l'elemento esattamente com'era.
 *
 * Cross-origin: un MediaElementAudioSourceNode la cui risorsa è CORS-cross-origin
 * emette SILENZIO — per specifica viene azzerata l'uscita, non solo l'analisi.
 * Quindi le sorgenti di terzi (le preview iTunes/Bandcamp di Discovery) non si
 * innestano affatto: suonano dall'elemento, senza spettro. Si analizzano solo le
 * tracce possedute, che passano dal proxy /api di Next e sono di pari origine
 * (vedi next.config.ts). */

type Graph = {
  ctx: AudioContext;
  analyser: AnalyserNode;
  // `<ArrayBuffer>` esplicito: `getByteFrequencyData` non accetta la vista
  // generica su ArrayBufferLike (potrebbe essere condivisa).
  freq: Uint8Array<ArrayBuffer>;
};

const FFT_SIZE = 1024;

type Ctor = typeof AudioContext;

let graph: Graph | null = null;
let primed = false;
const attached = new WeakSet<HTMLMediaElement>();

function audioContextCtor(): Ctor | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & { webkitAudioContext?: Ctor };
  return window.AudioContext ?? w.webkitAudioContext ?? null;
}

function ensureGraph(): Graph | null {
  if (graph) return graph;
  const Ctor = audioContextCtor();
  if (!Ctor) return null;
  try {
    const ctx = new Ctor();
    const analyser = ctx.createAnalyser();
    // 1024 = 512 bin, ~47Hz per bin a 48kHz: abbastanza fine da isolare la
    // cassa (47–190Hz) dal resto. Lo smoothing lo fa il nodo, così il disegno
    // non sfarfalla e non serve filtrare a valle.
    analyser.fftSize = FFT_SIZE;
    analyser.smoothingTimeConstant = 0.7;
    analyser.connect(ctx.destination);
    graph = { ctx, analyser, freq: new Uint8Array(analyser.frequencyBinCount) };
    return graph;
  } catch {
    return null;
  }
}

/** Crea e sblocca il contesto al primo gesto reale dell'utente. Idempotente:
 *  la chiamano sia la Home sia il trasporto, e i listener sono `once`. */
export function primeOnFirstGesture(): void {
  if (primed || typeof window === "undefined") return;
  primed = true;
  const unlock = () => {
    const g = ensureGraph();
    if (g && g.ctx.state !== "running") void g.ctx.resume();
  };
  for (const ev of ["pointerdown", "keydown"] as const) {
    window.addEventListener(ev, unlock, { once: true, passive: true });
  }
}

/** Vero solo per le sorgenti di pari origine, le uniche innestabili senza
 *  azzerare l'audio. Pura, così il test morda il caso che ha azzittito le
 *  preview di Discovery. */
export function isSameOriginSrc(src: string): boolean {
  if (!src) return false;
  try {
    return new URL(src, window.location.href).origin === window.location.origin;
  } catch {
    return false;
  }
}

/** Innesta l'elemento nel grafo, una sola volta per elemento. Non fa nulla se
 *  il contesto non è già in esecuzione: meglio nessuna analisi che un player
 *  muto. Il trasporto la richiama a ogni `play`, quindi il tentativo si ripete
 *  da sé al giro dopo. */
export function attachAnalyser(el: HTMLMediaElement | null | undefined): void {
  if (!el || attached.has(el)) return;
  // Sorgente di terzi: si esce PRIMA di toccare l'elemento. Innestarla
  // significherebbe azzittirla (vedi la nota cross-origin in testa al file).
  // Niente WeakSet: la sorgente dell'elemento può cambiare, e al prossimo
  // `play` la condizione si rivaluta.
  if (!isSameOriginSrc(el.currentSrc || el.src)) return;
  const g = ensureGraph();
  if (!g) return;
  if (g.ctx.state !== "running") {
    void g.ctx.resume();
    return;
  }
  let source: MediaElementAudioSourceNode;
  try {
    source = g.ctx.createMediaElementSource(el);
  } catch {
    // Già innestato altrove, o elemento non innestabile: si lascia stare.
    attached.add(el);
    return;
  }
  attached.add(el);
  try {
    source.connect(g.analyser);
  } catch {
    // Rete di sicurezza: l'uscita dell'elemento è ormai nel grafo, quindi
    // qualunque cosa accada deve comunque arrivare alle casse.
    try { source.connect(g.ctx.destination); } catch { /* nulla da fare */ }
  }
}

export type AudioLevels = {
  /** 0–1, energia di cassa (≈47–190Hz). */
  bass: number;
  /** 0–1, corpo (≈190Hz–2kHz): guida la densità dell'aria. */
  mid: number;
  /** Barre 0–1, spaziate in modo logaritmico: lo spettro disegnato. */
  bars: number[];
};

const BAR_FROM = 1;      // il bin 0 è la continua, non dice nulla
const BAR_TO = 220;      // oltre ~10kHz il contenuto è quasi sempre vuoto

/** Frequenza in Hz dei due estremi della scala disegnata: `edge` 0 = la banda
 *  più bassa, 1 = la più alta. Serve all'asse dello spettro, che senza numeri
 *  veri sarebbe una didascalia inventata. Fuori da un contesto audio vivo si
 *  usa 48kHz, il caso normale. */
export function bandEdgeHz(edge: 0 | 1): number {
  const rate = graph?.ctx.sampleRate ?? 48000;
  return (edge === 0 ? BAR_FROM : BAR_TO) * rate / FFT_SIZE;
}

/** Istantanea dei livelli, o null se non c'è nessun grafo (nessuna traccia
 *  posseduta ancora innestata, oppure Web Audio non disponibile). Mentre suona
 *  una sorgente di terzi il grafo resta fermo sull'ultima traccia analizzata e
 *  i valori decadono a zero: chi disegna lo tratta come silenzio. */
export function readLevels(barCount: number): AudioLevels | null {
  const g = graph;
  if (!g) return null;
  g.analyser.getByteFrequencyData(g.freq);
  const f = g.freq;

  const avg = (from: number, to: number) => {
    let sum = 0;
    const lo = Math.max(0, from);
    const hi = Math.min(f.length, to);
    if (hi <= lo) return 0;
    for (let i = lo; i < hi; i++) sum += f[i];
    return sum / (hi - lo) / 255;
  };

  const bars: number[] = [];
  // Spaziatura logaritmica: a spaziatura lineare le prime due barre
  // conterrebbero tutto il contenuto udibile e le altre resterebbero piatte.
  for (let b = 0; b < barCount; b++) {
    const lo = Math.round(BAR_FROM * Math.pow(BAR_TO / BAR_FROM, b / barCount));
    const hi = Math.round(BAR_FROM * Math.pow(BAR_TO / BAR_FROM, (b + 1) / barCount));
    bars.push(avg(lo, Math.max(lo + 1, hi)));
  }

  return { bass: avg(1, 5), mid: avg(5, 45), bars };
}

