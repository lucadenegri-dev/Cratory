/* La persona del frontespizio della Home (spec 2026-09-04): un easter egg.
   Con l'username SoundCloud salvato in Impostazioni uguale a `xgiorgix` la
   Home dice DJ GOODGIRL e la DJ nella cabina è una ragazza; per chiunque
   altro resta CRATORY. La decisione è tutta qui, pura e senza React, così la
   Home la applica e i test la coprono senza montare nulla. */

export type Persona = "cratory" | "goodgirl";

const GOODGIRL_USERNAME = "xgiorgix";

/** `username` è quello di `GET /api/soundcloud/status` (già senza `@` e
 *  spazi ai bordi: li toglie il backend al salvataggio). */
export function personaFor(username: string | null | undefined): Persona {
  return (username ?? "").trim().toLowerCase() === GOODGIRL_USERNAME ? "goodgirl" : "cratory";
}
