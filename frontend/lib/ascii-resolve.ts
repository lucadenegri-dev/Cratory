/* L'ingresso della Home: l'arte ascii non compare, si *risolve*. A progresso 0
   il blocco è rumore pieno, a 1 è il disegno finale; in mezzo i caratteri si
   assestano con una spazzata da sinistra, sfrangiata da un disturbo per cella
   così il fronte non è una riga netta.

   Puro e deterministico (nessun Math.random): stesso progresso, stesso
   fotogramma. Serve sia ai test sia al fatto che due componenti sulla stessa
   pagina si risolvano in modo coerente invece di scintillare ognuno per conto
   suo. */

/* Solo glifi presenti in DM Mono, come il resto dell'arte: i blocchi pieni
   unicode cadrebbero sul font di fallback con un'altra larghezza e
   disallineerebbero le colonne. */
const NOISE = "#/\\|-=+*:.·°";

/** Hash intero → [0,1). Mescolatore a 32 bit (xorshift-multiply), niente stato. */
function hash01(x: number, y: number, seed: number): number {
  let h = (Math.imul(x, 0x27d4eb2d) ^ Math.imul(y, 0x165667b1) ^ Math.imul(seed, 0x9e3779b9)) >>> 0;
  h = (h ^ (h >>> 15)) >>> 0;
  h = Math.imul(h, 0x2545f491) >>> 0;
  // `>>> 0` anche qui: lo XOR ridà un intero con segno, e senza questa
  // normalizzazione l'ultimo passaggio restituiva valori negativi.
  h = (h ^ (h >>> 13)) >>> 0;
  return h / 4294967296;
}

/** Fotogramma della risoluzione al progresso `p` (0→1, fuori range viene
 *  bloccato). A p >= 1 restituisce le righe identiche all'originale, stessa
 *  lunghezza a ogni p: l'impaginazione non può saltare durante l'ingresso. */
export function resolveLines(lines: string[], p: number, seed = 7): string[] {
  const progress = p <= 0 ? 0 : p >= 1 ? 1 : p;
  if (progress >= 1) return lines;
  const cols = Math.max(1, ...lines.map((l) => l.length));
  return lines.map((line, row) => {
    let out = "";
    for (let col = 0; col < line.length; col++) {
      // 0.55 di spazzata + 0.45 di disturbo: il fronte avanza da sinistra ma
      // resta frastagliato. La soglia sta sempre sotto 1, quindi a p=1 tutto
      // è risolto anche senza il ritorno anticipato qui sopra.
      const threshold = (col / cols) * 0.55 + hash01(col, row, seed) * 0.45;
      if (progress >= threshold) {
        out += line[col];
      } else {
        const n = Math.floor(hash01(row, col, seed + 1) * NOISE.length);
        out += NOISE[Math.min(NOISE.length - 1, n)];
      }
    }
    return out;
  });
}

/** Accelerazione dell'ingresso: parte veloce e si posa (quart out). */
export function easeOutQuart(t: number): number {
  const x = t <= 0 ? 0 : t >= 1 ? 1 : t;
  return 1 - Math.pow(1 - x, 4);
}
