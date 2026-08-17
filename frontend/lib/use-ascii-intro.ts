"use client";

import { useEffect, useSyncExternalStore } from "react";
import { easeOutQuart } from "@/lib/ascii-resolve";

const SESSION_KEY = "cratory:home-intro";

/* Progresso condiviso da tutta la pagina, non uno per componente: il
   frontespizio e la cabina devono risolversi sulla stessa onda, e la cabina
   monta dopo (aspetta i dati). Con uno stato per componente il primo a montare
   marcava la sessione e il secondo saltava l'ingresso del tutto.
   Un solo rAF per pagina, un solo valore, tanti sottoscrittori. */
let progress = 1;
let started = false;
const listeners = new Set<() => void>();

function set(v: number) {
  progress = v;
  for (const l of listeners) l();
}

function skipIntro(): boolean {
  if (typeof window === "undefined") return true;
  try {
    if (window.sessionStorage.getItem(SESSION_KEY) === "1") return true;
  } catch {
    // Storage negato (modalità privata, policy): l'ingresso parte comunque.
  }
  return typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function start(durationMs: number) {
  if (started) return;
  started = true;
  if (skipIntro()) return;
  try { window.sessionStorage.setItem(SESSION_KEY, "1"); } catch { /* vedi sopra */ }

  let t0 = 0;
  const step = (now: number) => {
    if (t0 === 0) t0 = now;
    const k = (now - t0) / durationMs;
    if (k >= 1) { set(1); return; }
    set(easeOutQuart(k));
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}

/** Progresso 0→1 dell'ingresso «risoluzione dal rumore», una volta per sessione.
 *
 *  Parte da 1, cioè dall'arte finita: è quello che rendono il server e un
 *  client senza JS, quindi niente disallineamento in hydration e nessun rischio
 *  di spedire una pagina di rumore. Il fotogramma zero lo scrive il primo rAF,
 *  quindi l'arte vera resta a schermo un fotogramma prima di scomporsi. Con
 *  `prefers-reduced-motion`, o dalla seconda visita in poi, non parte nulla. */
export function useAsciiIntro(durationMs = 850): number {
  const p = useSyncExternalStore(subscribe, () => progress, () => 1);
  useEffect(() => { start(durationMs); }, [durationMs]);
  return p;
}
