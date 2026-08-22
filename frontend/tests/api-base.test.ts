import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const base = readFileSync(resolve(__dirname, "../lib/api/base.ts"), "utf8");
const core = readFileSync(resolve(__dirname, "../lib/api/client.ts"), "utf8");
const organize = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("base URL del backend", () => {
  it("un solo punto la decide", () => {
    expect(base).toContain("NEXT_PUBLIC_API_URL");
    // Nessuno degli altri due la ricalcola per conto proprio: due punti che
    // decidono la stessa cosa divergono, ed e' il difetto che questo task chiude.
    expect(core).not.toContain("NEXT_PUBLIC_API_URL");
    expect(organize).not.toContain("NEXT_PUBLIC_API_URL");
  });

  it("entrambi i client la importano da li'", () => {
    expect(core).toContain("API_BASE");
    expect(organize).toContain("API_BASE");
  });

  it("il default resta il path relativo, cioe' il comportamento di oggi", () => {
    expect(base).toMatch(/\?\?\s*""/);
  });
});
