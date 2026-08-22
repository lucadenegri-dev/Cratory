import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../components/player-transport.tsx"), "utf8");

describe("l'elemento audio dichiara l'origine incrociata", () => {
  it('ha crossOrigin="anonymous"', () => {
    // Nel bundle desktop la pagina sta su tauri://localhost e l'audio su
    // http://127.0.0.1:8000. Senza la dichiarazione, createMediaElementSource
    // restituisce una sorgente tainted e l'analizzatore legge zeri: lo spettro
    // della Home resta a terra, senza un errore che lo spieghi.
    expect(source).toMatch(/<audio[\s\S]{0,900}crossOrigin="anonymous"/);
  });
});
