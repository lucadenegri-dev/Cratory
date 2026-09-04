"use client";

import { useEffect, useRef } from "react";
import { readLevels } from "@/lib/audio-analyser";

/* L'aria della Home, estesa a tutta la composizione: finora il pulviscolo
   viveva solo nelle tre righe sopra la cabina, dove al massimo si vedevano due
   glifi per volta. Qui sale per l'intera altezza del frontespizio, dietro il
   nome e attorno alla consolle.
 *
 * Sta in CSS, non in React: le particelle sono animate da un keyframe e non
 * ridisegnano nulla a ogni fotogramma. L'unico legame col suono è una custom
 * property (`--air-glow`) scritta su un solo elemento — nessun setState, quindi
 * nessun re-render, e con la scheda in secondo piano l'animazione si ferma da
 * sola come deve.
 *
 * Stessa tavolozza di glifi della cabina: solo caratteri che DM Mono ha
 * davvero, altrimenti cadrebbero sul font di fallback. */

/* Solo pulviscolo: `*` e `°` erano due glifi troppo grafici per un fondo. */
const GLYPHS = ["·", ".", "'", ","] as const;

/* L'easter egg (spec 2026-09-04): con la persona goodgirl un terzo del
   pulviscolo è fatto di cuori. Il cuore non sta in DM Mono e cade sul font di
   fallback — qui è accettabile, a differenza della cabina e della scritta:
   ogni particella è un elemento posizionato per conto suo, non una cella di
   una griglia, quindi la larghezza del glifo non sposta nulla. */
export const HEART = "♥";
export const HEART_GLYPHS = ["·", ".", HEART, "'", ",", HEART] as const;

/** A musica ferma il campo non si vede affatto: non basta fermarlo, deve
 *  proprio sparire. */
export const AIR_IDLE_GLOW = 0;
/** Luminosità minima mentre suona: da lì in su la portano i medi. */
export const AIR_PLAY_FLOOR = 0.38;

export type AirParticle = {
  /** Percentuale della larghezza. */
  left: number;
  /** Negativo: ogni particella entra già a metà corsa, così il campo è pieno
   *  dal primo fotogramma invece di riempirsi in mezzo minuto. */
  delay: number;
  duration: number;
  /** Corpo del carattere in rem. */
  size: number;
  /** Oscillazione orizzontale in px a metà salita. */
  drift: number;
  /** Quota percentuale che la particella occupa a corsa iniziata: serve solo a
   *  `prefers-reduced-motion`, dove il campo è fermo e il ritardo non
   *  distribuisce più nulla. */
  top: number;
  /** Un sesto delle particelle è "vicino": inchiostro `fg` invece di `muted`.
   *  Un campo tutto uguale legge come una texture; due piani danno profondità. */
  near: boolean;
  glyph: string;
};

/* Stesso mescolatore a 32 bit di lib/ascii-resolve (normalizzato dopo ogni
   XOR: senza, torna negativo). Deterministico per indice, quindi server e
   client generano lo stesso campo e l'hydration non se ne accorge. */
function hash01(i: number, salt: number): number {
  let h = (Math.imul(i + 1, 0x27d4eb2d) ^ Math.imul(salt + 1, 0x165667b1)) >>> 0;
  h = (h ^ (h >>> 15)) >>> 0;
  h = Math.imul(h, 0x2545f491) >>> 0;
  h = (h ^ (h >>> 13)) >>> 0;
  return h / 4294967296;
}

/** Il campo, derivato dall'indice: puro e deterministico, mai Math.random. */
export function airParticles(
  count: number, seed = 0, glyphs: readonly string[] = GLYPHS,
): AirParticle[] {
  return Array.from({ length: count }, (_, i) => {
    const duration = 16 + hash01(i, seed + 2) * 22;
    const elapsed = hash01(i, seed + 3);          // frazione di corsa già fatta
    return {
      left: 2 + hash01(i, seed + 1) * 96,
      duration,
      delay: -elapsed * duration,
      size: 0.55 + hash01(i, seed + 4) * 0.5,
      drift: (hash01(i, seed + 5) - 0.5) * 52,
      top: 100 - elapsed * 100,                   // sale dal basso: 100% → 0%
      near: hash01(i, seed + 7) < 0.18,
      glyph: glyphs[Math.floor(hash01(i, seed + 6) * glyphs.length) % glyphs.length],
    };
  });
}

const COUNT = 120;
const PARTICLES = airParticles(COUNT);
/* Stesso seme: i cuori prendono il posto di alcune particelle, il campo non
   si ridistribuisce. */
const HEART_PARTICLES = airParticles(COUNT, 0, HEART_GLYPHS);

/** Lo strato, dietro alla composizione. `active` = dall'app esce suono: allora
 *  la luminosità segue i medi della traccia, altrimenti resta al valore di
 *  riposo. Con `hearts` un terzo delle particelle è un cuore in danger.
 *  Decorativo e inerte al puntatore. */
export function AsciiAtmosphere({ active, hearts = false }: {
  active: boolean;
  /** Cuori fra il pulviscolo: l'easter egg DJ GOODGIRL. */
  hearts?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const particles = hearts ? HEART_PARTICLES : PARTICLES;

  const glow = useRef(AIR_IDLE_GLOW);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const step = () => {
      const levels = active ? readLevels(1) : null;
      // I medi, non i bassi: la cassa la porta già la cabina, e legare anche
      // l'aria al colpo farebbe lampeggiare tutta la pagina a tempo.
      const target = active
        ? Math.min(0.95, AIR_PLAY_FLOOR + (levels?.mid ?? 0) * 0.6)
        : AIR_IDLE_GLOW;
      glow.current += (target - glow.current) * 0.12;   // inseguimento morbido
      // Spegnendosi il ciclo si chiude da sé: nessun frame chiesto a vuoto
      // mentre la pagina è ferma.
      if (!active && glow.current < 0.004) {
        el.style.setProperty("--air-glow", "0");
        return;
      }
      el.style.setProperty("--air-glow", glow.current.toFixed(3));
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [active]);

  return (
    /* `air-still` congela il campo dov'è (animation-play-state) invece di
       azzerarlo: stessa dottrina del fermo immagine della cabina — se non esce
       suono, in pagina non si muove nulla. */
    <div ref={ref} aria-hidden="true"
      className={`pointer-events-none absolute inset-0 select-none overflow-hidden${active ? "" : " air-still"}`}>
      {particles.map((p, i) => (
        <span key={i}
          className={`${p.near ? "air air-near" : "air"}${p.glyph === HEART ? " air-heart" : ""}`}
          style={{
            left: `${p.left.toFixed(2)}%`,
            fontSize: `${p.size.toFixed(2)}rem`,
            animationDuration: `${p.duration.toFixed(2)}s`,
            animationDelay: `${p.delay.toFixed(2)}s`,
            ["--air-drift" as string]: `${p.drift.toFixed(1)}px`,
            ["--air-top" as string]: `${p.top.toFixed(1)}%`,
          }}>
          {p.glyph}
        </span>
      ))}
    </div>
  );
}
