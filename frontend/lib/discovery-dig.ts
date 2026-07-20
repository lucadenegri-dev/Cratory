// Vocabolario condiviso di una query di dig: tipo di seme e preset di profondita'.
// Sta in lib/ perche' sia il componente UI (DiscoveryDigBar) sia la logica pura
// (discovery-surprise) ne dipendano senza che la lib importi dal componente.

export type SeedType = "genre" | "label";

/** DOVE si pesca nella pila ordinata per domanda. Non e' un mix di ordinamento:
 *  sceglie il bacino (vedi spec del motore, `_window`). */
export const DEPTHS = [
  { key: "surface", value: 0.0 },
  { key: "mid", value: 0.5 },
  { key: "deep", value: 1.0 },
] as const;
