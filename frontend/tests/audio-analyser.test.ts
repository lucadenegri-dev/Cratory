import { describe, expect, it } from "vitest";

import { isSameOriginSrc } from "@/lib/audio-analyser";

/* Il guardiano che tiene in vita l'audio delle preview di Discovery.
   Innestare un elemento cross-origin in un MediaElementAudioSourceNode ne
   azzera l'uscita (per specifica: silenzio, non solo analisi cieca), ed è
   esattamente il bug che ha azzittito il player del dig. */
describe("isSameOriginSrc", () => {
  it("accetta le tracce possedute, che passano dal proxy /api di Next", () => {
    expect(isSameOriginSrc("/api/tracks/12/audio")).toBe(true);
    expect(isSameOriginSrc(`${window.location.origin}/api/tracks/12/audio`)).toBe(true);
  });

  it("rifiuta le sorgenti di terzi: innestarle vorrebbe dire azzittirle", () => {
    expect(isSameOriginSrc("https://audio-ssl.itunes.apple.com/preview.m4a")).toBe(false);
    expect(isSameOriginSrc("https://t4.bcbits.com/stream/abc/mp3-128/1")).toBe(false);
    // Stesso host, porta diversa: è comunque un'altra origine.
    expect(isSameOriginSrc("http://localhost:9999/api/tracks/12/audio")).toBe(false);
  });

  it("senza sorgente non innesta nulla", () => {
    expect(isSameOriginSrc("")).toBe(false);
  });

  // Forma reale che vale la pena coprire: senza schema l'URL eredita quello
  // della pagina, ma l'host resta di terzi.
  it("riconosce come esterna anche una sorgente senza schema", () => {
    expect(isSameOriginSrc("//audio-ssl.itunes.apple.com/preview.m4a")).toBe(false);
  });
});
