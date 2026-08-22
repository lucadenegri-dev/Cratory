import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

/* Asserzioni sul sorgente, non sul rendering: queste pagine sono grosse,
   montano provider e chiamano il backend al mount, quindi un render in vitest
   fallirebbe per ragioni estranee a cio' che va provato. Il vero cancello
   comportamentale e' `CRATORY_STATIC_EXPORT=1 npm run build` nel Task 5 — che
   oggi fallisce ed e' esattamente cio' che questa conversione ripara — piu' la
   verifica manuale in fondo a questo task. Stesso pattern di
   tests/organize-api-base.test.ts. */
const leggi = (p: string) => readFileSync(resolve(__dirname, "..", p), "utf8");

describe("le rotte di dettaglio leggono l'id dalla query", () => {
  it("tracks non e' piu' un segmento dinamico", () => {
    expect(existsSync(resolve(__dirname, "../app/tracks/[id]"))).toBe(false);
    expect(existsSync(resolve(__dirname, "../app/tracks/page.tsx"))).toBe(true);
  });

  it("playlists sta sotto detail, perche' /playlists e' gia' la lista", () => {
    expect(existsSync(resolve(__dirname, "../app/playlists/[id]"))).toBe(false);
    expect(existsSync(resolve(__dirname, "../app/playlists/detail/page.tsx"))).toBe(true);
  });

  it("nessuna delle due prende piu' l'id da `params`", () => {
    for (const p of ["app/tracks/page.tsx", "app/playlists/detail/page.tsx"]) {
      const src = leggi(p);
      expect(src, p).toContain("useSearchParams");
      expect(src, p).not.toContain("Promise<{ id: string }>");
      expect(src, p).not.toMatch(/use\(params\)/);
    }
  });

  it("nessun link punta piu' a un segmento dinamico", () => {
    const sorgenti = ["app/library/page.tsx", "app/transitions/page.tsx",
                      "components/wishlist-row.tsx", "components/library-track-grid.tsx",
                      "components/organize/files-table.tsx", "app/playlists/page.tsx",
                      // Non nella tabella del brief: il player docked condiviso linka
                      // anche lui al dettaglio traccia (cover/titolo della "now playing").
                      "components/docked-player.tsx"];
    for (const p of sorgenti) {
      // Il template `/tracks/${...}` e `/playlists/${...}`: le rotte statiche
      // /playlists/import-* non hanno interpolazione e non combaciano.
      expect(leggi(p), p).not.toMatch(/["`]\/(?:tracks|playlists)\/\$\{/);
    }
  });
});

describe("sets, labels e shazam", () => {
  it("nessuno e' piu' un segmento dinamico", () => {
    for (const vecchia of ["app/sets/[id]", "app/labels/[label]", "app/shazam/[id]"]) {
      expect(existsSync(resolve(__dirname, "..", vecchia)), vecchia).toBe(false);
    }
    for (const nuova of ["app/sets/detail/page.tsx", "app/labels/detail/page.tsx",
                         "app/shazam/detail/page.tsx"]) {
      expect(existsSync(resolve(__dirname, "..", nuova)), nuova).toBe(true);
    }
  });

  it("hanno il confine Suspense che useSearchParams richiede", () => {
    for (const p of ["app/sets/detail/page.tsx", "app/labels/detail/page.tsx",
                     "app/shazam/detail/page.tsx"]) {
      expect(leggi(p), p).toContain("<Suspense>");
    }
  });

  it("labels non ri-decodifica il valore", () => {
    // useSearchParams ha gia' decodificato una volta: una seconda passata
    // corrompe le etichette con % (URIError, pagina schiantata) e con %26,
    // che diventa silenziosamente &. Questo e' solo il pin della regressione
    // esatta (il sorgente non deve ricontenere la chiamata); il comportamento
    // a runtime e' provato in tests/labels-detail-decode.test.tsx, che
    // renderizza davvero la pagina con un % letterale nella label.
    expect(leggi("app/labels/detail/page.tsx")).not.toContain("decodeURIComponent");
  });
});
