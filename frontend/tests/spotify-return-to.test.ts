import { describe, expect, it } from "vitest";

import { urlDiRitorno } from "@/lib/api/base";

/* Dove il backend deve riportare l'utente a fine OAuth Spotify.
 *
 * Il difetto che questo copre: il callback rimandava sempre alla prima origine
 * di FRONTEND_ORIGIN (http://localhost:3000), che nel bundle desktop non
 * esiste — la pagina sta su tauri://localhost. La destinazione ora la dice la
 * pagina, e calcolarla e' l'unico punto in cui si puo' sbagliare.
 *
 * `location.origin` NON e' utilizzabile: per uno schema non speciale come
 * `tauri:` la specifica dice che l'origine e' opaca, cioe' la stringa "null"
 * — il backend riceverebbe "null/setup" e la scarterebbe come non valida,
 * ricadendo sulla destinazione morta di partenza. Da qui protocol+host. */

describe("urlDiRitorno", () => {
  it("nel bundle desktop tiene lo schema custom, dove location.origin direbbe 'null'", () => {
    expect(urlDiRitorno("tauri://localhost/setup")).toBe("tauri://localhost/setup");
  });

  it("nel browser e' l'origine e il percorso della pagina", () => {
    expect(urlDiRitorno("http://localhost:3000/settings")).toBe("http://localhost:3000/settings");
  });

  it("scarta query e fragment: quella query la riscrive il callback", () => {
    expect(urlDiRitorno("http://localhost:3000/settings?spotify=error&detail=x#giu"))
      .toBe("http://localhost:3000/settings");
  });

  it("tiene la porta: e' parte dell'origine, e senza il backend non riconosce la pagina", () => {
    expect(urlDiRitorno("http://localhost:3001/setup")).toBe("http://localhost:3001/setup");
  });

  it("la radice resta la radice, non una stringa senza percorso", () => {
    expect(urlDiRitorno("tauri://localhost/")).toBe("tauri://localhost/");
  });

  it("un href che non e' un URL non produce una destinazione inventata", () => {
    expect(urlDiRitorno("questo-non-e-un-url")).toBe("");
  });
});
