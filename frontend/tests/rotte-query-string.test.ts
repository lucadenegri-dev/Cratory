import { describe, expect, it } from "vitest";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

/* Asserzioni sul sorgente, non sul rendering: queste pagine sono grosse,
   montano provider e chiamano il backend al mount, quindi un render in vitest
   fallirebbe per ragioni estranee a cio' che va provato. Il vero cancello
   comportamentale e' `CRATORY_STATIC_EXPORT=1 npm run build` nel Task 5 — che
   oggi fallisce ed e' esattamente cio' che questa conversione ripara — piu' la
   verifica manuale in fondo a questo task. Stesso pattern di
   tests/organize-api-base.test.ts. */
const leggi = (p: string) => readFileSync(resolve(__dirname, "..", p), "utf8");

/** Ogni sorgente del frontend (esclusi i test e gli artefatti di build). */
function sorgenti(): string[] {
  const radice = resolve(__dirname, "..");
  const salta = new Set(["node_modules", ".next", "out", "tests", "e2e", "test-results"]);
  const out: string[] = [];
  const scendi = (dir: string) => {
    for (const voce of readdirSync(dir, { withFileTypes: true })) {
      if (voce.name.startsWith(".") || salta.has(voce.name)) continue;
      const pieno = join(dir, voce.name);
      if (voce.isDirectory()) scendi(pieno);
      else if (/\.tsx?$/.test(voce.name)) out.push(relative(radice, pieno));
    }
  };
  scendi(radice);
  return out;
}

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

  it("nessun link punta piu' a un segmento dinamico, in nessun sorgente", () => {
    // Setaccio su tutto il frontend, non su un elenco di file compilato a mano:
    // un elenco resta indietro appena qualcuno aggiunge un sito di link (e' gia'
    // successo — components/docked-player.tsx mancava dal brief). Copre tutte e
    // cinque le rotte, non solo le due del primo giro.
    //
    // Il pattern vuole l'apice/backtick SUBITO prima del segmento, quindi i path
    // dell'API (`/api/tracks/${id}`) non combaciano, e le rotte statiche
    // (/playlists/import-*) non hanno interpolazione.
    const vietato = /["`]\/(?:tracks|playlists|sets|labels|shazam)\/\$\{/;
    for (const p of sorgenti()) {
      expect(leggi(p), p).not.toMatch(vietato);
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
