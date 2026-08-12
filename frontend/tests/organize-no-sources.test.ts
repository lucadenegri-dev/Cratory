import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const api = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("le sorgenti non sono più un concetto della UI", () => {
  it("la pagina /organize/sources non esiste", () => {
    expect(existsSync(resolve(__dirname, "../app/organize/sources/page.tsx"))).toBe(false);
  });

  it("il client API non espone più le funzioni sulle sorgenti", () => {
    for (const fn of ["listSources", "addSource", "deleteSource", "setRootTarget"]) {
      expect(api).not.toContain(`export function ${fn}`);
    }
  });

  it("nessuna chiamata residua a /sources o /settings/roots", () => {
    expect(api).not.toContain("/sources");
    expect(api).not.toContain("/settings/roots");
  });
});
