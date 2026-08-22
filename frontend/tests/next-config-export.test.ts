import { afterEach, describe, expect, it, vi } from "vitest";

/* Cancello comportamentale, non testuale: si importa davvero next.config.ts
   nei due modi e si guarda l'oggetto che produce. Un `output: "export"` reso
   incondizionato — ovunque lo si scriva nell'oggetto — fa fallire il primo
   test, ed e' la regressione che romperebbe `npm run dev`, l'HMR e la suite
   E2E su :3211. */

async function config(staticExport: boolean) {
  vi.resetModules();
  if (staticExport) process.env.CRATORY_STATIC_EXPORT = "1";
  else delete process.env.CRATORY_STATIC_EXPORT;
  return (await import("../next.config")).default;
}

afterEach(() => {
  delete process.env.CRATORY_STATIC_EXPORT;
  vi.resetModules();
});

describe("modo di build statico", () => {
  it("senza la variabile: niente export e il proxy /api/* c'e' ancora", async () => {
    const cfg = await config(false);
    expect(cfg.output).toBeUndefined();
    expect(cfg.rewrites).toBeTypeOf("function");
    expect(await cfg.rewrites!()).toEqual([
      { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" },
    ]);
  });

  it("con la variabile: export acceso e nessun rewrite", async () => {
    const cfg = await config(true);
    expect(cfg.output).toBe("export");
    // Non "inerte": proprio assente. Next non applicherebbe i rewrites senza un
    // server, e lasciarli direbbe il falso a chi legge la config.
    expect(cfg.rewrites).toBeUndefined();
  });

  it("si accende solo con \"1\", non con un valore qualsiasi", async () => {
    vi.resetModules();
    process.env.CRATORY_STATIC_EXPORT = "0";
    const cfg = (await import("../next.config")).default;
    expect(cfg.output).toBeUndefined();
  });
});
