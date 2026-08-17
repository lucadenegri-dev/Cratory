"use client";

import { useEffect, useRef } from "react";
import { bandEdgeHz, readLevels } from "@/lib/audio-analyser";
import { useT } from "@/lib/i18n";

/* Lo spettro di quello che sta suonando, staccato dalla cabina: una striscia a
   piena larghezza sul piede della composizione. Le tre righe ASCII sotto la
   console erano illeggibili — tre soglie fisse quantizzavano tutto e il blocco
   si confondeva con il disegno del DJ. Qui le barre sono elementi veri ad
   altezza continua, la stessa grammatica dell'istogramma BPM (dashboard e
   /statistics): asse in basso, bassi a sinistra, acuti a destra, estremi in
   hertz.

   Sopra ogni banda, la scia del picco: una colonna traslucida che resta dove
   il segnale è appena stato e ricade più lentamente della barra (il
   comportamento dei VU meter), chiusa in cima da un filo di `fg-strong`.
   Barra piena, scia diluita, filo netto: tre densità dello stesso inchiostro —
   la gerarchia monocroma del sistema, nessuna tinta.

   Le 60 letture al secondo scrivono `transform` (e l'opacità delle tacche)
   direttamente sui ref: nessun setState, nessun re-render, niente layout (solo
   composito). Con la scheda in secondo piano il rAF si sospende da solo. */

export const SPECTRUM_BANDS = 48;

/** Pavimento delle barre mentre suona: anche le bande vuote mostrano un filo
 *  d'inchiostro, così si vede che la scala è fatta di 48 misure. */
const BAR_FLOOR = 0.04;
/** Caduta della tacca di picco per frame (~60/s): da fondo scala a zero in
 *  circa due secondi. La salita invece è istantanea, spinta dalla barra. */
const CAP_FALL = 0.008;
/** Spessore del filo di picco, lo stesso del notch dell'Equalizer. */
const CAP_PX = 2;

/** Il passo della tacca: sale subito col segnale, scende a velocità costante,
 *  mai sotto la barra né sotto zero. Pura, così il test morde l'invariante
 *  «la tacca non sta mai sotto la barra». */
export function fallPeak(prev: number, level: number): number {
  return Math.max(level, prev - CAP_FALL, 0);
}

/** Hz formattati come li vuole l'asse: interi sotto il kilo, con una cifra
 *  sopra. Pura, così il test ne sorveglia gli estremi. */
export function formatHz(hz: number): string {
  return hz >= 1000 ? `${(hz / 1000).toFixed(1).replace(/\.0$/, "")} kHz` : `${Math.round(hz)} Hz`;
}

/** La striscia. `active` = dall'app esce suono: allora compare — barre, filetto
 *  e asse insieme. A riposo sparisce del tutto (opacity, non unmount: lo spazio
 *  resta riservato e la composizione non sobbalza quando parte la musica),
 *  coerente con la regola della pagina: a musica ferma non si vede nulla di
 *  vivo. */
export function SpectrumStrip({ active }: { active: boolean }) {
  const t = useT();
  const wrap = useRef<HTMLDivElement>(null);
  const bars = useRef<(HTMLSpanElement | null)[]>([]);
  const trails = useRef<(HTMLSpanElement | null)[]>([]);
  const caps = useRef<(HTMLSpanElement | null)[]>([]);
  const peaks = useRef<Float64Array>(new Float64Array(SPECTRUM_BANDS));

  useEffect(() => {
    const setBar = (i: number, v: number) => {
      const el = bars.current[i];
      if (el) el.style.transform = `scaleY(${v.toFixed(3)})`;
    };
    const setTrail = (i: number, v: number) => {
      const el = trails.current[i];
      if (el) el.style.transform = `scaleY(${v.toFixed(3)})`;
    };
    const setCap = (i: number, v: number, visible: boolean) => {
      const el = caps.current[i];
      if (!el) return;
      el.style.transform = `translateY(${(-v).toFixed(1)}px)`;
      el.style.opacity = visible ? "1" : "0";
    };
    if (!active) {
      peaks.current.fill(0);
      for (let i = 0; i < SPECTRUM_BANDS; i++) { setBar(i, 0); setTrail(i, 0); setCap(i, 0, false); }
      return;
    }
    let raf = 0;
    const step = () => {
      const levels = readLevels(SPECTRUM_BANDS);
      if (levels) {
        // Corsa della tacca in px, misurata sul contenitore vero: resta giusta
        // anche se un domani h-12 cambia.
        const travel = (wrap.current?.clientHeight ?? 48) - CAP_PX;
        const p = peaks.current;
        for (let i = 0; i < SPECTRUM_BANDS; i++) {
          const v = Math.max(BAR_FLOOR, levels.bars[i] ?? 0);
          setBar(i, v);
          p[i] = fallPeak(p[i], v);
          // La scia sta DIETRO la barra: si vede solo il tratto fra barra e
          // picco, che è esattamente il segnale appena passato.
          setTrail(i, p[i]);
          // Sul pavimento il filo si nasconde: 48 trattini allineati in basso
          // sarebbero una linea di base, non un'informazione.
          setCap(i, p[i] * travel, p[i] > BAR_FLOOR + 0.02);
        }
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [active]);

  return (
    <div aria-hidden="true"
      className={`select-none transition-opacity duration-300 ${active ? "opacity-100" : "opacity-0"}`}>
      <div ref={wrap} className="flex h-12 items-end gap-px border-b border-border">
        {Array.from({ length: SPECTRUM_BANDS }, (_, i) => (
          <span key={i} className="relative h-full flex-1">
            <span
              ref={(el) => { trails.current[i] = el; }}
              className="absolute inset-0 origin-bottom bg-fg opacity-25"
              style={{ transform: "scaleY(0)" }}
            />
            <span
              ref={(el) => { bars.current[i] = el; }}
              className="absolute inset-0 origin-bottom bg-fg"
              style={{ transform: "scaleY(0)" }}
            />
            <span
              ref={(el) => { caps.current[i] = el; }}
              className="absolute inset-x-0 bottom-0 h-[2px] bg-fg-strong"
              style={{ transform: "translateY(0)", opacity: 0 }}
            />
          </span>
        ))}
      </div>
      {/* L'asse: frequenze vere, dal sample rate del contesto audio
          (lib/audio-analyser.ts). La dissolvenza la porta il contenitore. */}
      <div className="mt-1.5 flex items-baseline justify-between text-[10px] uppercase tracking-wider text-muted">
        <span className="tnum">{formatHz(bandEdgeHz(0))}</span>
        <span className="text-faint">{t.dashboard.spectrumLabel}</span>
        <span className="tnum">{formatHz(bandEdgeHz(1))}</span>
      </div>
    </div>
  );
}
