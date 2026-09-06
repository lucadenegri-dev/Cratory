// Vocabolario condiviso di una query di dig: tipo di seme e preset di profondita'.
// Sta in lib/ perche' sia il componente UI (DiscoveryDigBar) sia la logica pura
// (discovery-surprise) ne dipendano senza che la lib importi dal componente.

export type SeedType = "genre" | "label";

export type DigSourceKey = "discogs" | "bandcamp";

/** DOVE si pesca nella pila ordinata per domanda. Non e' un mix di ordinamento:
 *  sceglie il bacino (vedi spec del motore, `_window`). */
export const DEPTHS = [
  { key: "surface", value: 0.0 },
  { key: "mid", value: 0.5 },
  { key: "deep", value: 1.0 },
] as const;

/** Quanti item scarica un dig: rispecchia WINDOW_ITEMS del backend. Sotto questa
 *  soglia la finestra è l'intera pila e la profondità non ha niente da scegliere. */
export const WINDOW_ITEMS = 300;

/** L'URL della modalità simili. Unica fonte per bottone, interruttore e rilancio.
 *
 *  `from` è l'origine da cui si è arrivati alla traccia (la libreria coi suoi
 *  filtri, una playlist...): viaggia fin qui perché il link "torna alla traccia"
 *  possa restituirla alla traccia INTATTA, con la sua stessa memoria. Senza,
 *  la catena si spezza al primo passo indietro e si riatterra sulla libreria
 *  nuda. Chi lo LEGGE deve validarlo: qui si trasporta e basta. */
export function similarHref(
  trackId: number,
  stylePeriod: boolean,
  from?: string | null,
): string {
  const params = new URLSearchParams();
  params.set("similar", String(trackId));
  params.set("style_period", stylePeriod ? "1" : "0");
  if (from) params.set("from", from);
  return `/discovery?${params.toString()}`;
}
