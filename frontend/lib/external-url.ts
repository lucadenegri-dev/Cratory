"use client";

/* Portare fuori i link esterni, nel guscio desktop.
 *
 * Nel browser `target="_blank"` apre una scheda e non c'e' niente da fare. Nel
 * webview di Tauri no: WKWebView chiede al delegato di creare la nuova vista
 * (`webView:createWebViewWithConfiguration:forNavigationAction:`), e siccome
 * Tauri non registra nessun gestore di nuove finestre il delegato risponde
 * "niente". Nessuna scheda, nessun errore, nessun suono: il click cade nel
 * vuoto. E' il motivo per cui nell'app impacchettata i link a Spotify,
 * SoundCloud, Discogs, alla documentazione e alla web UI di slskd non facevano
 * assolutamente nulla.
 *
 * La cura sta in un punto solo (un ascoltatore in fase di cattura montato dal
 * guscio, vedi components/external-link-bridge.tsx) e non nei tredici file che
 * scrivono `target="_blank"`: quelli restano ancore normali, corrette nel
 * browser, e chi ne aggiunge una domani non deve ricordarsi di niente. */

import { isOwnUrl } from "@/lib/api/base";

type ConTauri = Window & { __TAURI_INTERNALS__?: unknown };

/** La pagina gira dentro il guscio desktop e non in un browser. Tauri inietta
 *  `__TAURI_INTERNALS__` prima di ogni script della pagina: e' la stessa spia
 *  che usa `isTauri()` di @tauri-apps/api. */
export function isDesktopShell(): boolean {
  return typeof window !== "undefined" && (window as ConTauri).__TAURI_INTERNALS__ !== undefined;
}

/** Vero per gli URL che vanno consegnati al browser di sistema: web pubblico,
 *  cioe' http(s) che non sia roba nostra.
 *
 *  Il filtro su http(s) non e' una formalita': nel bundle gli URL interni sono
 *  `tauri://localhost/...` e gli export passano da `blob:`, e ne' gli uni ne'
 *  gli altri hanno senso fuori. Il filtro su "roba nostra" tiene dentro anche
 *  il backend, che nel bundle e' http://127.0.0.1:8000 e quindi sarebbe
 *  altrimenti indistinguibile da un sito qualunque. */
export function isExternalUrl(url: string): boolean {
  if (typeof window === "undefined") return false;
  let u: URL;
  try {
    u = new URL(url, window.location.href);
  } catch {
    return false;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  return !isOwnUrl(u.href);
}

/** Consegna l'URL al programma predefinito del sistema. Import dinamico: nel
 *  build per il browser il codice del plugin non entra mai nel bundle
 *  iniziale, e senza guscio desktop non viene nemmeno scaricato. */
export async function openExternal(url: string): Promise<void> {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}
