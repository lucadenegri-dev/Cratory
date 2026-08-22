import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../next.config.ts"), "utf8");

describe("modo di build statico", () => {
  it("l'export si accende da variabile d'ambiente, non e' sempre attivo", () => {
    expect(source).toContain("CRATORY_STATIC_EXPORT");
    // Sempre attivo romperebbe `npm run dev`, l'HMR e la suite E2E.
    expect(source).not.toMatch(/output:\s*"export"\s*,?\s*\n\s*(async rewrites|allowedDevOrigins)/);
  });

  it("in export i rewrites non ci sono: Next non li applicherebbe comunque", () => {
    expect(source).toContain("rewrites");
    expect(source).toMatch(/ESPORTA|esporta|statico/);
  });
});
