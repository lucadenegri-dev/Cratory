/* Il frontespizio della Home: CRATORY a lettere piene. Stesso vocabolario
   grafico delle casse della cabina (`#########` in ascii-dj), così le due
   scritte sembrano fatte dello stesso materiale.
   Due strati come la cabina, ma qui il guscio è senza stato: questa è ferma, e
   la cabina resta l'unica cosa che si muove in pagina.
   Solo `#` e spazio: i glifi pieni unicode (█ ▓) cadono sul font di fallback
   con larghezza diversa e disallineano le colonne — la stessa ragione per cui
   la cabina usa `°*·` al posto di `♪♫`. */

const WORD = "CRATORY";

export const WORDMARK_ROWS = 5;

/* Glifi 5x5, solo le lettere che servono a CRATORY: un alfabeto completo
   sarebbe codice mai chiamato. Esportati perché il test ne sorvegli la
   geometria, che è ciò che tiene in riga le colonne. */
export const GLYPHS: Record<string, readonly string[]> = {
  C: ["#####",
      "#    ",
      "#    ",
      "#    ",
      "#####"],
  R: ["#### ",
      "#   #",
      "#### ",
      "#  # ",
      "#   #"],
  A: [" ### ",
      "#   #",
      "#####",
      "#   #",
      "#   #"],
  T: ["#####",
      "  #  ",
      "  #  ",
      "  #  ",
      "  #  "],
  O: [" ### ",
      "#   #",
      "#   #",
      "#   #",
      " ### "],
  Y: ["#   #",
      " # # ",
      "  #  ",
      "  #  ",
      "  #  "],
};

/** Compone una parola dai glifi, una colonna di spazio fra le lettere:
 *  WORDMARK_ROWS righe di larghezza uniforme. Deterministica, senza React.
 *  Nessun pareggiamento difensivo delle righe — la larghezza uniforme discende
 *  dalla geometria dei glifi, che è quel che il test verifica. */
export function wordmarkLines(word: string): string[] {
  const rows: string[] = [];
  for (let r = 0; r < WORDMARK_ROWS; r++) {
    rows.push(
      [...word]
        .map((ch) => {
          const glyph = GLYPHS[ch];
          if (!glyph) throw new Error(`ascii-wordmark: nessun glifo per "${ch}"`);
          return glyph[r];
        })
        .join(" "),
    );
  }
  return rows;
}

export const WORDMARK_LINES = wordmarkLines(WORD);

/** Il frontespizio: la parola in grande, ferma. L'arte è decorativa; il titolo
 *  vero della pagina è l'h1 accanto, che la Home altrimenti non avrebbe (non
 *  passa `title` a PageLayout).
 *  L'interlinea è più stretta di quella della cabina (1.15): lì il disegno è
 *  fatto di tratti (/ | \) e l'aria fra le righe serve a leggerli, qui le
 *  lettere sono blocchi pieni e a 1.15 le aste verticali si vedono
 *  tratteggiate. A 0.95 la parola si compatta con i contorni ancora aperti;
 *  sotto ~0.8 la A e la O si chiudono. Misurato in preview su DM Mono.
 *  `overflow-y-hidden` è esplicito perché con `overflow-x-auto` da solo il CSS
 *  promuove anche l'asse verticale ad `auto`, e bastava l'arrotondamento
 *  sub-pixel dell'inchiostro (l'interlinea sta sotto l'unità) per far comparire
 *  una barra di scorrimento verticale dentro la cornice. Il rientro in `em`
 *  sull'arte dà comunque l'aria che serve: non si ritaglia nulla, si toglie
 *  solo la barra. */
export function AsciiWordmark() {
  return (
    <div className="flex justify-center overflow-x-auto overflow-y-hidden">
      <h1 className="sr-only">Cratory</h1>
      <div
        aria-hidden="true"
        /* 12px sul telefono, non 13: 41 colonne per l'advance di DM Mono fanno
           295px, che stanno dentro i 309 che restano una volta tolti i margini
           della cornice. A 13px la scritta eccedeva e scrollava nel riquadro.
           Il rientro verticale in `em` restituisce lo spazio che l'interlinea a
           0.95 toglie: sotto l'unità l'inchiostro deborda dalla riga, e siccome
           `overflow-x-auto` sull'involucro costringe anche l'asse verticale ad
           `auto`, quei due pixel bastavano a far comparire una barra di
           scorrimento. In `em` perché l'eccedenza cresce col corpo. */
        className="select-none py-[0.15em] text-[12px] text-fg-strong sm:text-lg md:text-xl lg:text-2xl 2xl:text-3xl"
      >
        {WORDMARK_LINES.map((line, i) => (
          <pre key={i} className="leading-[0.95]">{line}</pre>
        ))}
      </div>
    </div>
  );
}
