import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const base = readFileSync(resolve(__dirname, "../lib/api/base.ts"), "utf8");
const core = readFileSync(resolve(__dirname, "../lib/api/client.ts"), "utf8");
const organize = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

/* Il difetto che questo task chiude: `lib/api/client.ts` aveva l'override della
   base URL e `lib/organize/api.ts` no, quindi in un build statico meta' app
   avrebbe perso le chiamate. La prova che conta e' quindi comportamentale —
   valorizzata la variabile, TUTTI E DUE i client devono puntare al backend —
   non testuale. */

/** Ricarica i moduli con NEXT_PUBLIC_API_URL al valore dato (undefined = assente). */
async function conBase(valore: string | undefined) {
  vi.resetModules();
  if (valore === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = valore;
  return {
    core: await import("@/lib/api/client"),
    organize: await import("@/lib/organize/api"),
  };
}

describe("base URL del backend: comportamento", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_API_URL;
    vi.resetModules();
  });

  it("assente: entrambi i client restano relativi, cioe' il comportamento di oggi", async () => {
    const m = await conBase(undefined);
    await m.core.apiGet("/api/tracks");
    await m.organize.libraryStats();
    const chiamate = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(chiamate[0]).toBe("/api/tracks");
    expect(chiamate[1]).toBe("/api/organize/library/stats");
  });

  it("valorizzata: la seguono entrambi, non solo quello che gia' l'aveva", async () => {
    const m = await conBase("http://127.0.0.1:8000");
    await m.core.apiGet("/api/tracks");
    await m.organize.libraryStats();
    const chiamate = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(chiamate[0]).toBe("http://127.0.0.1:8000/api/tracks");
    expect(chiamate[1]).toBe("http://127.0.0.1:8000/api/organize/library/stats");
  });
});

describe("base URL del backend: un solo punto la decide", () => {
  it("nessuno dei due client la ricalcola per conto proprio", () => {
    expect(base).toContain("NEXT_PUBLIC_API_URL");
    // Due punti che decidono la stessa cosa divergono: e' il difetto che questo
    // task chiude, e questo e' il pin della regressione esatta.
    expect(core).not.toContain("NEXT_PUBLIC_API_URL");
    expect(organize).not.toContain("NEXT_PUBLIC_API_URL");
  });

  it("entrambi la importano da li' (un'occorrenza in un commento non basta)", () => {
    for (const [nome, src] of [["client.ts", core], ["organize/api.ts", organize]] as const) {
      expect(src, nome).toMatch(/import\s*\{[^}]*\bAPI_BASE\b[^}]*\}\s*from\s*["']@\/lib\/api\/base["']/);
    }
  });
});
