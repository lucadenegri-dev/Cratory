import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const provider = readFileSync(resolve(__dirname, "../components/jobs-provider.tsx"), "utf8");

describe("un solo provider dei job", () => {
  it("il provider di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../components/organize/jobs-provider.tsx"))).toBe(false);
  });

  it("il layout di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../app/organize/layout.tsx"))).toBe(false);
  });

  it("una sola barra fissa in tutta la codebase", () => {
    const conta = (s: string) => (s.match(/fixed inset-x-0 bottom-0/g) ?? []).length;
    expect(conta(provider)).toBe(1);
  });

  it("le azioni di Organize sono sulla JobsApi unica", () => {
    for (const a of ["startScan", "startApply", "startRescan", "startIntegrity", "startGenreReview"]) {
      expect(provider).toContain(`${a},`);
    }
  });

  it("nessuna seconda riga per la scansione", () => {
    /* scan e libraryIndex sono lo stesso job da due endpoint: una seconda
       `track()` rimetterebbe in piedi la duplicazione che F5 toglie. Qui basta
       la struttura; che la riga sia davvero una sola, e che porti la fase, lo
       verifica jobs-provider-organize.test.tsx rendendo il componente. */
    expect((provider.match(/key: "library-index"/g) ?? [])).toHaveLength(1);
    expect(provider).not.toContain('key: "organize-scan"');
  });
});

/* Il riavvio automatico della scansione a fine apply NON si verifica qui: un
   test di testo sopravviverebbe alla riga commentata (provato: resta verde).
   Sta in jobs-provider-organize.test.tsx, che rende il provider e osserva la
   chiamata — con il caso negativo che ne prova la discriminazione. */
