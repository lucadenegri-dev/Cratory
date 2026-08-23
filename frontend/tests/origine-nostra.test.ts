import { describe, expect, it } from "vitest";

import { isOwnOrigin } from "@/lib/api/base";

/* Il guardiano che tiene in vita l'audio delle preview di Discovery e, insieme,
   lo spettro della Home.

   Innestare in un MediaElementAudioSourceNode una risorsa cross-origin che NON
   e' CORS-approvata ne azzera l'uscita (per specifica: silenzio, non solo
   analisi cieca), ed e' esattamente il bug che ha azzittito il player del dig.
   Ma "stessa origine" e' un guardiano troppo stretto: nel bundle desktop la
   pagina sta su tauri://localhost e il backend su http://127.0.0.1:8000, quindi
   nemmeno le tracce possedute passavano — spettro fermo, senza un errore che lo
   spieghi. Il confine giusto e' "roba nostra": la pagina stessa, oppure il
   backend, che ammette l'origin del webview nel CORS e viene richiesto con
   crossOrigin="anonymous". */

const WEB = "http://localhost:3000/";
const BUNDLE = "tauri://localhost/";
const BACKEND = "http://127.0.0.1:8000";

describe("isOwnOrigin, in sviluppo (pagina e backend sulla stessa origine)", () => {
  it("accetta le tracce possedute, che passano dal proxy /api di Next", () => {
    expect(isOwnOrigin("/api/tracks/12/audio", WEB, "")).toBe(true);
    expect(isOwnOrigin("http://localhost:3000/api/tracks/12/audio", WEB, "")).toBe(true);
  });

  it("rifiuta le sorgenti di terzi: innestarle vorrebbe dire azzittirle", () => {
    expect(isOwnOrigin("https://audio-ssl.itunes.apple.com/preview.m4a", WEB, "")).toBe(false);
    expect(isOwnOrigin("https://t4.bcbits.com/stream/abc/mp3-128/1", WEB, "")).toBe(false);
    // Stesso host, porta diversa: e' comunque un'altra origine.
    expect(isOwnOrigin("http://localhost:9999/api/tracks/12/audio", WEB, "")).toBe(false);
  });

  it("senza sorgente non innesta nulla", () => {
    expect(isOwnOrigin("", WEB, "")).toBe(false);
  });

  // Forma reale che vale la pena coprire: senza schema l'URL eredita quello
  // della pagina, ma l'host resta di terzi.
  it("riconosce come esterna anche una sorgente senza schema", () => {
    expect(isOwnOrigin("//audio-ssl.itunes.apple.com/preview.m4a", WEB, "")).toBe(false);
  });
});

describe("isOwnOrigin, nel bundle desktop (pagina su tauri://, backend su 127.0.0.1)", () => {
  it("accetta le tracce possedute servite dal backend: e' il caso che teneva fermo lo spettro", () => {
    expect(isOwnOrigin(`${BACKEND}/api/tracks/12/audio`, BUNDLE, BACKEND)).toBe(true);
  });

  it("rifiuta comunque le sorgenti di terzi", () => {
    expect(isOwnOrigin("https://audio-ssl.itunes.apple.com/preview.m4a", BUNDLE, BACKEND)).toBe(false);
    expect(isOwnOrigin("https://t4.bcbits.com/stream/abc/mp3-128/1", BUNDLE, BACKEND)).toBe(false);
  });

  it("rifiuta un altro backend sulla stessa macchina", () => {
    expect(isOwnOrigin("http://127.0.0.1:9999/api/tracks/12/audio", BUNDLE, BACKEND)).toBe(false);
  });

  // tauri: non e' uno schema "speciale": la sua origin secondo la specifica URL
  // e' opaca, cioe' la stringa "null". Confrontando le origin cosi' come sono,
  // QUALUNQUE altro URL a origin opaca (data:, un altro schema custom) sarebbe
  // scambiato per la pagina stessa. Qui si morde proprio quello.
  it("non scambia per propria un'altra origine opaca", () => {
    expect(isOwnOrigin("data:audio/mpeg;base64,AAAA", BUNDLE, BACKEND)).toBe(false);
    expect(isOwnOrigin("altroschema://localhost/x.mp3", BUNDLE, BACKEND)).toBe(false);
  });

  it("accetta una risorsa della pagina stessa", () => {
    expect(isOwnOrigin("tauri://localhost/silenzio.mp3", BUNDLE, BACKEND)).toBe(true);
  });
});
