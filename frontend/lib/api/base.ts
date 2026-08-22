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
