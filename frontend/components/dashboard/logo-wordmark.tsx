"use client";

/* Il frontespizio della Home: CRATORY nell'alfabeto «Corrosione», le stesse
   lame della C del marchio (`frontend/app/icon.svg`).
   Prima era arte ASCII di `#`, dello stesso materiale della cabina: con il
   marchio nuovo la parola passa a tracciati veri. Restano SVG e non un'immagine
   per due motivi che qui contano entrambi: scala fino alla larghezza dello
   schermo senza sfocare, e prende il colore dal testo — un PNG nero sparirebbe
   sul tema scuro.
   L'ingresso non puo' piu' «risolversi dal rumore» (non ci sono caratteri da
   scomporre): le lettere entrano una dopo l'altra sulla stessa onda della
   cabina, che quel rumore continua a farlo. */

import { useMemo } from "react";
import {
  GLYPHS, GLYPH_FILL_RULE, GLYPH_MARGIN, type Glyph,
} from "@/components/dashboard/logo-glyphs";
import { useAsciiIntro } from "@/lib/use-ascii-intro";

const WORD = "CRATORY";

/** Altezza comune delle maiuscole, in unita' del viewBox composto. */
export const CAP_HEIGHT = 1000;

/** Aria fra due lettere. La tavola le disegna quasi a contatto, ma li' sono un
 *  campionario: in parola serve respiro, o le punte di una entrano nell'altra.
 *  Misurato a schermo: sotto ~40 le lame si toccano, sopra ~150 la parola si
 *  sfilaccia in sette segni separati. */
export const TRACKING = 90;

/** Larghezza dello spazio, per l'easter egg «DJ GOODGIRL». Non e' un glifo
 *  come gli altri (non ha inchiostro): e' solo avanzamento. */
export const SPACE_ADVANCE = 260;

export type Placed = {
  ch: string;
  /** Scala da applicare al tracciato del glifo. */
  scale: number;
  /** Traslazione del gruppo, gia' comprensiva del margine del file sorgente. */
  x: number;
  y: number;
  /** Larghezza dell'inchiostro una volta scalato: serve ai test e al layout. */
  width: number;
  glyph: Glyph;
};

export type Layout = { width: number; height: number; items: Placed[] };

/** Mette in riga le lettere di `word`.
 *
 *  Ogni lettera viene scalata per conto suo fino a `CAP_HEIGHT` e appoggiata
 *  sulla stessa linea di base. La tavola sorgente non ha ne' l'una ne' l'altra
 *  cosa — le lettere sono allineate in cima e alte quanto capita, perche' e' un
 *  campionario e non una parola composta — e prendere le sue proporzioni alla
 *  lettera lasciava la O piccola e la A a mezz'aria. Scalare ciascuna in modo
 *  UNIFORME (mai in altezza soltanto) tiene intatta la forma di ognuna e
 *  pareggia solo la statura.
 *
 *  Pura: niente React, cosi' il test puo' misurarne la geometria. */
export function wordmarkLayout(word: string, tracking = TRACKING): Layout {
  const items: Placed[] = [];
  let x = 0;
  for (const ch of word) {
    if (ch === " ") {
      x += SPACE_ADVANCE + tracking;
      continue;
    }
    const glyph = GLYPHS[ch];
    if (!glyph) throw new Error(`logo-wordmark: nessun glifo per "${ch}"`);
    const scale = CAP_HEIGHT / glyph.h;
    const width = glyph.w * scale;
    // Il tracciato sorgente parte a (GLYPH_MARGIN, GLYPH_MARGIN): la
    // traslazione lo toglie, cosi' `x` e' davvero il bordo dell'inchiostro e le
    // spaziature non dipendono dal margine di chi ha esportato il file.
    items.push({
      ch,
      scale,
      x: x - GLYPH_MARGIN * scale,
      y: -GLYPH_MARGIN * scale,
      width,
      glyph,
    });
    x += width + tracking;
  }
  return { width: Math.max(0, x - tracking), height: CAP_HEIGHT, items };
}

/** Opacita' della lettera `i` di `n` a un dato punto dell'ingresso.
 *
 *  Le lettere non entrano tutte insieme ne' una alla volta in fila indiana: le
 *  finestre si sovrappongono, se no l'ultima arriverebbe molto dopo che la
 *  cabina ha finito di risolversi. Con `progress` a 1 vale 1 per tutte, che e'
 *  quello che rendono il server e un client senza JS. */
export function letterOpacity(i: number, n: number, progress: number): number {
  if (progress >= 1 || n <= 0) return 1;
  const finestra = 0.55;                       // quanto dura l'entrata di una lettera
  const inizio = n === 1 ? 0 : (i / (n - 1)) * (1 - finestra);
  return Math.min(1, Math.max(0, (progress - inizio) / finestra));
}

export function LogoWordmark({ word = WORD, title = "Cratory", className }: {
  /** La parola composta. L'easter egg passa "DJ GOODGIRL". */
  word?: string;
  /** Il testo dell'h1 nascosto: deve dire cio' che l'arte mostra. */
  title?: string;
  className?: string;
} = {}) {
  const intro = useAsciiIntro();
  const layout = useMemo(() => wordmarkLayout(word), [word]);
  const n = layout.items.length;
  return (
    <div className="flex justify-center">
      <h1 className="sr-only">{title}</h1>
      <svg
        aria-hidden="true"
        viewBox={`0 0 ${layout.width.toFixed(0)} ${layout.height}`}
        /* `currentColor` e non un colore scritto: e' cosi' che la scritta
           segue il tema, come faceva l'arte ASCII prendendo `text-fg-strong`. */
        fill="currentColor"
        /* Senza questa regola gli occhielli si riempiono e la O diventa un
           rombo nero: sta nei file sorgente, e va portata fin qui. */
        fillRule={GLYPH_FILL_RULE as "evenodd" | "nonzero"}
        className={className ?? "h-auto w-full max-w-5xl text-fg-strong"}
      >
        {layout.items.map((it, i) => (
          <g
            key={`${it.ch}-${i}`}
            transform={`translate(${it.x.toFixed(2)} ${it.y.toFixed(2)}) scale(${it.scale.toFixed(4)})`}
            opacity={letterOpacity(i, n, intro)}
          >
            <path d={it.glyph.d} />
          </g>
        ))}
      </svg>
    </div>
  );
}
