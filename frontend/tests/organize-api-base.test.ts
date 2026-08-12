import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("client API Organize", () => {
  it("usa un path relativo (nessun URL assoluto verso il backend)", () => {
    expect(source).not.toContain("8010");
    expect(source).not.toContain("localhost:8000");
    expect(source).not.toContain("NEXT_PUBLIC_API_BASE");
    expect(source).not.toMatch(/https?:\/\//);
    expect(source).toContain('const API = "/api/organize"');
  });

  it("prefissa tutte le chiamate con /api/organize", () => {
    expect(source).toContain("/api/organize");
  });

  it("non contiene più path che iniziano con /api/ non prefissati", () => {
    const nudi = source.match(/"\/api\/(?!organize)[a-z-]+/g) ?? [];
    expect(nudi).toEqual([]);
  });
});
