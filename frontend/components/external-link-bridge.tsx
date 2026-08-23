"use client";

import { useEffect } from "react";

import { isDesktopShell, isExternalUrl, openExternal } from "@/lib/external-url";

/** Il ponte fra le ancore della pagina e il browser di sistema, montato una
 *  volta dal layout. Nel browser non fa nulla: `target="_blank"` funziona da
 *  se'. Nel guscio desktop intercetta il click e apre l'URL fuori — senza
 *  questo il click non fa niente del tutto (vedi lib/external-url.ts).
 *
 *  Un solo ascoltatore su `document`, in fase di CATTURA: deve arrivare prima
 *  dei gestori dei componenti — `next/link` intercetta il click per conto suo,
 *  e i menu chiudono il pannello — altrimenti la navigazione partirebbe
 *  comunque. Non rende inerte niente in fase di bolla: chi ha gia' fatto
 *  `preventDefault` (bottoni disabilitati travestiti da link) viene lasciato
 *  stare. */
export function ExternalLinkBridge() {
  useEffect(() => {
    if (!isDesktopShell()) return;
    const onClick = (e: MouseEvent) => {
      // Click primario e nudo: il resto (tasto centrale, Cmd-click) e' gia'
      // "apri altrove" e non passa comunque dal webview.
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const target = e.target;
      if (!(target instanceof Element)) return;
      const a = target.closest("a[href]");
      if (!(a instanceof HTMLAnchorElement)) return;
      // Un download e' un'altra faccenda: mandarlo al browser di sistema
      // significherebbe scaricarlo due volte, o non scaricarlo affatto.
      if (a.hasAttribute("download")) return;
      if (!isExternalUrl(a.href)) return;
      e.preventDefault();
      void openExternal(a.href);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);
  return null;
}
