/** L'unico punto che decide dove sta il backend.
 *
 *  Vuota = stesso host della pagina: le chiamate `/api/*` passano dal rewrite
 *  di `next.config.ts`, e l'app funziona anche aperta da un altro dispositivo
 *  in LAN. In un build statico quel rewrite non esiste — non c'e' nessun
 *  server Next — e la variabile punta il client direttamente al backend.
 *
 *  Sta qui e non nei due client perche' erano due: `lib/api/client.ts` aveva
 *  l'override, `lib/organize/api.ts` no, e meta' app avrebbe perso le chiamate. */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Schema+host+porta di `url`, risolto contro `base`, o null se non e' un URL.
 *
 *  Non si usa `URL.origin`: `tauri:` non e' uno schema "speciale" e la sua
 *  origin secondo la specifica e' opaca, cioe' la stringa "null". Confrontando
 *  le origin cosi' come sono, nel bundle desktop qualunque altro URL a origin
 *  opaca (un `data:`, un altro schema custom) risulterebbe di pari origine con
 *  la pagina. Qui l'identita' e' esplicita e regge anche per tauri://localhost. */
function chiaveOrigine(url: string, base: string): string | null {
  try {
    const u = new URL(url, base);
    return `${u.protocol}//${u.host}`;
  } catch {
    return null;
  }
}

/** `url` e' roba nostra — la pagina stessa o il backend?
 *
 *  Sono due casi e non uno, ed e' il punto: in sviluppo il backend E' la
 *  pagina (proxy `/api/*` di Next, `apiBase` vuota); nel bundle desktop la
 *  pagina sta su tauri://localhost e il backend su http://127.0.0.1:8000, due
 *  origini diverse che restano entrambe nostre. Confonderle con un unico
 *  "stessa origine" e' cio' che ha tenuto a terra lo spettro della Home.
 *
 *  Pura nei suoi tre argomenti, cosi' il test morde i due mondi senza dover
 *  fingere ne' `window` ne' l'ambiente di build. */
export function isOwnOrigin(url: string, pageHref: string, apiBase: string): boolean {
  if (!url) return false;
  const origine = chiaveOrigine(url, pageHref);
  if (!origine) return false;
  if (origine === chiaveOrigine(pageHref, pageHref)) return true;
  // apiBase vuota = il backend e' la pagina stessa: il confronto qui sopra ha
  // gia' detto tutto.
  if (!apiBase) return false;
  return origine === chiaveOrigine(apiBase, pageHref);
}

/** `isOwnOrigin` con la pagina e il backend di questa app. Fuori dal browser
 *  (prerender) non c'e' nessuna pagina rispetto a cui giudicare: falso. */
export function isOwnUrl(url: string): boolean {
  if (typeof window === "undefined") return false;
  return isOwnOrigin(url, window.location.href, API_BASE);
}
