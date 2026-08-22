import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("client API Organize", () => {
  it("non contiene un URL assoluto verso il backend", () => {
    expect(source).not.toContain("8010");
    expect(source).not.toContain("localhost:8000");
    expect(source).not.toMatch(/https?:\/\//);
    // La base non e' piu' un letterale qui: la decide lib/api/base.ts, e il
    // prefisso /api/organize ci si compone sopra.
    expect(source).toContain("API_BASE");
    expect(source).toContain("/api/organize");
  });

  it("prefissa tutte le chiamate con /api/organize", () => {
    expect(source).toContain("/api/organize");
  });

  it("non contiene più path che iniziano con /api/ non prefissati", () => {
    const nudi = source.match(/"\/api\/(?!organize)[a-z-]+/g) ?? [];
    expect(nudi).toEqual([]);
  });
});
