#!/usr/bin/env python3
"""Genera il dizionario dei glifi della scritta CRATORY dai singoli SVG.

Sorgente: `svg/<LETTERA>.svg`, uno per lettera, con `fill="currentColor"` e un
viewBox che e' il rettangolo d'inchiostro della lettera piu' 12 unita' di
margine per lato. Qui si estrae il tracciato cosi' com'e' — nessuna
riscrittura delle coordinate, cosi' un confronto col sorgente resta leggibile —
e si annota quanto misura l'inchiostro, che e' cio' che serve al compositore
per allineare le lettere.

Uso, dalla radice del repository:

    python3 assets/branding/alfabeto-corrosione/genera-glifi.py \\
        > frontend/components/dashboard/logo-glyphs.ts
"""
import pathlib
import re
import sys

# Solo le lettere che la Home compone davvero: CRATORY e, per l'easter egg
# (spec 2026-09-04), DJ GOODGIRL. La tavola ne ha 26; imbarcare le altre
# quindici sarebbe peso spedito a ogni visita e mai disegnato.
LETTERE = "ACDGIJLORTY"
MARGINE = 12.0

QUI = pathlib.Path(__file__).resolve().parent


def leggi(ch: str) -> tuple[str, float, float, str]:
    testo = (QUI / "svg" / f"{ch}.svg").read_text(encoding="utf-8")
    vb = re.search(r'viewBox="([-\d.\s]+)"', testo)
    d = re.search(r'\sd="([^"]+)"', testo)
    if vb is None or d is None:
        raise SystemExit(f"{ch}.svg: manca viewBox o path")
    # La regola di riempimento NON e' un dettaglio: e' cio' che tiene vuoti gli
    # occhielli. Perderla per strada riempie la O e la fa diventare un rombo
    # nero. Si legge dal file invece di darla per scontata.
    fr = re.search(r'fill-rule="([^"]+)"', testo)
    if fr is None:
        raise SystemExit(f"{ch}.svg: manca fill-rule")
    _, _, vw, vh = (float(x) for x in vb.group(1).split())
    return d.group(1).strip(), vw - 2 * MARGINE, vh - 2 * MARGINE, fr.group(1)


def main() -> None:
    righe = []
    regole = set()
    for ch in LETTERE:
        d, w, h, regola = leggi(ch)
        regole.add(regola)
        righe.append(f'  {ch}: {{ w: {w:g}, h: {h:g}, d: "{d}" }},')
    # Una sola regola per tutte, o il compositore non puo' metterla una volta
    # sola sull'SVG. Meglio fermarsi qui che disegnare una lettera piena.
    if len(regole) != 1:
        raise SystemExit(f"fill-rule non uniforme fra le lettere: {sorted(regole)}")
    regola = regole.pop()

    print(f'''/* GENERATO — non modificare a mano.
   Sorgente: assets/branding/alfabeto-corrosione/svg/<LETTERA>.svg
   Rigenera: python3 assets/branding/alfabeto-corrosione/genera-glifi.py \\
               > frontend/components/dashboard/logo-glyphs.ts

   Le lettere dell'alfabeto «Corrosione», nello stile della C del marchio.
   `d` e' il tracciato come sta nel file sorgente, quindi nel SUO sistema di
   coordinate: l'inchiostro parte a {MARGINE:g},{MARGINE:g} ed e' grande `w` x `h`. A
   metterle in riga pensa il compositore (logo-wordmark.tsx), che di ognuna
   ha bisogno solo di quanto misura. */

/** Il margine attorno all'inchiostro dentro il viewBox di ogni file. */
export const GLYPH_MARGIN = {MARGINE:g};

/** Come riempire i tracciati. Gli occhielli (la pancia della O, il triangolo
 *  della A) sono vuoti solo con questa regola: senza, la O e' un rombo pieno. */
export const GLYPH_FILL_RULE = "{regola}";

export type Glyph = {{ w: number; h: number; d: string }};

export const GLYPHS: Record<string, Glyph> = {{
{chr(10).join(righe)}
}};''')


if __name__ == "__main__":
    sys.exit(main())
