import { describe, expect, it } from "vitest";

import { resolveBackLink, sectionOf, withFrom, type BackLinkFallback, type SectionKey } from "@/lib/back-link";

const LABELS: Record<SectionKey, string> = {
  library: "Libreria",
  playlists: "Playlists",
  labels: "Etichette",
  sets: "Set",
  transitions: "Transizioni",
  downloads: "Wishlist",
  shazam: "Shazam",
};
const FALLBACK: BackLinkFallback = { href: "/library", labelKey: "library" };

describe("resolveBackLink", () => {
  it("senza `from` usa il fallback della pagina", () => {
    expect(resolveBackLink(null, FALLBACK, LABELS)).toEqual({ href: "/library", label: "Libreria" });
  });

  it("torna alla pagina di provenienza con l'etichetta della sua sezione", () => {
    expect(resolveBackLink("/playlists/7", FALLBACK, LABELS)).toEqual({
      href: "/playlists/7",
      label: "Playlists",
    });
  });

  it("conserva la query dell'origine: filtri e paginazione non si perdono", () => {
    const from = "/library?artist=Simon+%26+Garfunkel&offset=50";
    expect(resolveBackLink(from, FALLBACK, LABELS)).toEqual({ href: from, label: "Libreria" });
  });

  it("rifiuta un `from` che punta fuori dall'app", () => {
    for (const evil of ["//evil.com", "/\\evil.com", "https://evil.com", "evil.com", ""]) {
      expect(resolveBackLink(evil, FALLBACK, LABELS)).toEqual({ href: "/library", label: "Libreria" });
    }
  });

  it("rifiuta una rotta interna che non è una sezione nota", () => {
    expect(resolveBackLink("/settings", FALLBACK, LABELS)).toEqual({ href: "/library", label: "Libreria" });
  });
});

describe("sectionOf", () => {
  it("riconosce la sezione dal segmento di rotta, non da un prefisso parziale", () => {
    expect(sectionOf("/sets/12")).toBe("sets");
    expect(sectionOf("/sets")).toBe("sets");
    // /set-builder non è /sets: un match per prefisso nudo lo prenderebbe per errore.
    expect(sectionOf("/set-builder")).toBeNull();
  });

  it("ignora la query quando riconosce la sezione", () => {
    expect(sectionOf("/library?artist=A")).toBe("library");
  });

  it("riconosce le rotte di dettaglio nella loro forma attuale (a query string)", () => {
    // Il `from` che le pagine di dettaglio si costruiscono da sole dopo il
    // passaggio alla query string: se `detail` non risolvesse alla sezione
    // giusta, il link "indietro" mostrerebbe l'etichetta del fallback.
    expect(sectionOf("/playlists/detail?id=7")).toBe("playlists");
    expect(sectionOf("/sets/detail?id=12")).toBe("sets");
    expect(sectionOf("/labels/detail?label=Ostgut%20Ton")).toBe("labels");
    expect(sectionOf("/shazam/detail?id=3")).toBe("shazam");
  });
});

describe("withFrom", () => {
  it("codifica l'origine, query compresa", () => {
    expect(withFrom("/tracks/42", "/library?artist=A&offset=50")).toBe(
      "/tracks/42?from=%2Flibrary%3Fartist%3DA%26offset%3D50",
    );
  });
});

describe("withFrom con un href che ha già una query", () => {
  it("usa & invece di ? quando la query c'è già", () => {
    expect(withFrom("/tracks?id=42", "/library")).toBe("/tracks?id=42&from=%2Flibrary");
  });

  it("usa ancora ? quando la query non c'è", () => {
    expect(withFrom("/library", "/")).toBe("/library?from=%2F");
  });

  it("non ri-codifica un href che contiene già un valore percent-encoded", () => {
    // /labels?label=Ostgut%20Ton: il valore è già codificato dal chiamante e
    // withFrom non deve toccarlo, solo appendere il proprio parametro.
    expect(withFrom("/labels?label=Ostgut%20Ton", "/labels")).toBe(
      "/labels?label=Ostgut%20Ton&from=%2Flabels",
    );
  });
});
