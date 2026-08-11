import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("client API Organize", () => {
  it("punta al backend unico, non alla vecchia porta 8010", () => {
    expect(source).not.toContain("8010");
    expect(source).toContain("http://localhost:8000");
  });

  it("prefissa tutte le chiamate con /api/organize", () => {
    expect(source).toContain("/api/organize");
  });

  it("non contiene più path che iniziano con /api/ non prefissati", () => {
    const nudi = source.match(/"\/api\/(?!organize)[a-z-]+/g) ?? [];
    expect(nudi).toEqual([]);
  });
});
