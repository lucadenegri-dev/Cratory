import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { en } from "../lib/i18n/en";
import { it as itDict } from "../lib/i18n/it";

/** Foglie del dizionario, come percorsi puntati: serve a confrontare en e it. */
function chiavi(o: object, prefisso = ""): string[] {
  return Object.entries(o).flatMap(([k, v]) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? chiavi(v as object, `${prefisso}${k}.`)
      : [`${prefisso}${k}`]);
}

describe("dizionario unico", () => {
  it("il dizionario di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../lib/organize/i18n"))).toBe(false);
  });

  it("le chiavi di Organize vivono sotto organize.*", () => {
    expect(en.organize).toBeDefined();
    expect(itDict.organize).toBeDefined();
    expect(chiavi(en.organize).length).toBeGreaterThan(100);
  });

  it("en e it hanno le stesse chiavi sotto organize (nessuna persa nel travaso)", () => {
    expect(chiavi(itDict.organize).sort()).toEqual(chiavi(en.organize).sort());
  });

  it("i codici errore di Organize stanno al livello dove translateApiError li cerca", () => {
    /* translateApiError legge DICTIONARIES[lang].errors[code]: se i codici di
       Organize finissero sotto organize.errors smetterebbero di essere tradotti,
       in silenzio. */
    for (const code of ["scan_running", "picker_unavailable"]) {
      expect(en.errors[code]).toBeDefined();
      expect(itDict.errors[code]).toBeDefined();
    }
  });

  it("nessun file importa più il dizionario di Organize", () => {
    const conta = (p: string) =>
      (readFileSync(resolve(__dirname, p), "utf8").match(/organize\/i18n/g) ?? []).length;
    expect(conta("../lib/i18n/en.ts")).toBe(0);
    expect(conta("../lib/i18n/it.ts")).toBe(0);
  });
});
