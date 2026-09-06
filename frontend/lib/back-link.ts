"use client";

import { useSearchParams } from "next/navigation";

import { useT } from "@/lib/i18n";

/** Le sezioni a cui una pagina di dettaglio può appartenere: rotta -> chiave in t.nav. */
const SECTIONS = [
  ["/library", "library"],
  ["/playlists", "playlists"],
  ["/labels", "labels"],
  ["/sets", "sets"],
  ["/transitions", "transitions"],
  ["/wishlist", "downloads"],
  ["/shazam", "shazam"],
] as const;

export type SectionKey = (typeof SECTIONS)[number][1];
export type BackLink = { href: string; label: string };
/** Dove tornare quando `from` manca o non è valido (ingresso diretto, link condiviso). */
export type BackLinkFallback = { href: string; labelKey: SectionKey };

/** Un path interno e innocuo: niente URL assoluti, niente `//host` o `/\host`
 *  (che i browser trattano come protocol-relative, cioè come uscita dall'app).
 *  Esportata perché è la stessa regola ovunque un `from` che arriva dall'URL
 *  diventi un href — qui e nella modalità simili di Discovery. */
export function isInternalPath(path: string): boolean {
  return path.startsWith("/") && path[1] !== "/" && path[1] !== "\\";
}

/** La sezione a cui appartiene un path interno, o null se non è una rotta nota.
 *  Il confronto è per segmento: "/set-builder" non è la sezione "/sets". */
export function sectionOf(path: string): SectionKey | null {
  const route = path.split("?")[0];
  for (const [prefix, key] of SECTIONS) {
    if (route === prefix || route.startsWith(`${prefix}/`)) return key;
  }
  return null;
}

/** Il link "indietro" di una pagina di dettaglio. `from` è il valore del param
 *  omonimo GIÀ decodificato una volta da useSearchParams: non ri-decodificarlo,
 *  altrimenti i valori con &, % o # si corrompono e i filtri ripristinati saltano.
 *  Pura di proposito: la logica si testa senza React. */
export function resolveBackLink(
  from: string | null,
  fallback: BackLinkFallback,
  labels: Record<SectionKey, string>,
): BackLink {
  const section = from && isInternalPath(from) ? sectionOf(from) : null;
  if (!from || !section) return { href: fallback.href, label: labels[fallback.labelKey] };
  return { href: from, label: labels[section] };
}

/** Versione hook di resolveBackLink: legge `from` dall'URL e le etichette da i18n. */
export function useBackLink(fallback: BackLinkFallback): BackLink {
  const t = useT();
  const searchParams = useSearchParams();
  return resolveBackLink(searchParams.get("from"), fallback, t.nav);
}

/** Appende `from=<origine>` a un link verso una pagina di dettaglio.
 *  Il separatore dipende da `href`: dopo il passaggio delle rotte di dettaglio
 *  alla query string (`/tracks?id=42`) un `?` fisso produrrebbe un secondo
 *  punto interrogativo, e `id` varrebbe letteralmente "42?from=%2Flibrary". */
export function withFrom(href: string, from: string): string {
  const separatore = href.includes("?") ? "&" : "?";
  return `${href}${separatore}from=${encodeURIComponent(from)}`;
}
