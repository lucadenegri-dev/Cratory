/* Quali passi ha il wizard, e perche' non sono sempre gli stessi.
 *
 * Vive qui e non dentro app/setup/page.tsx perche' quello e' un file di route:
 * Next.js valida quali export sono ammessi in una pagina, e uno arbitrario
 * farebbe fallire il build. */

const TUTTI = ["welcome", "prerequisites", "library", "services", "summary"] as const;
export type Passo = (typeof TUTTI)[number];

/** Cio' che serve sapere di un componente per decidere: se c'e', e da dove
 *  viene. Volutamente piu' largo di `ProbeComponent` — questa funzione non ha
 *  bisogno d'altro, e i test possono passarle due campi invece di dodici. */
type Componente = { present: boolean; source: string | null };

/* Il passo dei prerequisiti esiste per far installare ffmpeg e fpcalc. Nel
   bundle viaggiano dentro l'app: non c'e' niente da installare e niente da
   scegliere, quindi il passo non si monta affatto -- cosi' il contatore
   "passo N di M" resta onesto invece di saltare un numero. Basta un
   componente che NON venga dal bundle perche' il passo torni.

   `null` (probe non ancora risposto) e lista vuota tengono il passo: toglierlo
   e rimetterlo sotto gli occhi dell'utente sarebbe peggio che mostrarlo un
   istante di troppo, e `every` su una lista vuota e' vero — senza il controllo
   sulla lunghezza, non sapere niente equivarrebbe a sapere che va tutto bene. */
export function passiDelWizard(componenti: Componente[] | null): Passo[] {
  const tuttoDalBundle =
    componenti !== null &&
    componenti.length > 0 &&
    componenti.every((c) => c.present && c.source === "bundle");
  return TUTTI.filter((p) => p !== "prerequisites" || !tuttoDalBundle);
}
