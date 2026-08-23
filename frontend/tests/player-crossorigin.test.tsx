import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PlayerTransport } from "@/components/player-transport";

/* Chi chiede il permesso CORS e chi no.
 *
 * Le sorgenti nostre lo chiedono: nel bundle desktop la pagina sta su
 * tauri://localhost e il backend su http://127.0.0.1:8000, e senza
 * crossOrigin="anonymous" createMediaElementSource riceve una risorsa
 * non CORS-approvata — l'analizzatore legge zeri e lo spettro della Home resta
 * a terra, senza un errore che lo spieghi.
 *
 * Le sorgenti di terzi NON lo chiedono, ed è altrettanto vincolante: lo stesso
 * elemento suona le preview del dig, e t4.bcbits.com non risponde con
 * Access-Control-Allow-Origin. Chiedere il permesso a chi non lo concede non
 * degrada l'analisi: fa fallire il caricamento, cioè zittisce la preview.
 * Tanto quelle non si innestano comunque nel grafo (vedi isOwnOrigin). */

afterEach(cleanup);

function crossOriginDi(src: string): string | null {
  cleanup();
  render(<PlayerTransport src={src} testId="audio" onAudible={() => {}} />);
  return (screen.getByTestId("audio") as HTMLAudioElement).getAttribute("crossorigin");
}

describe("l'elemento audio dichiara l'origine incrociata solo per le sorgenti nostre", () => {
  it("traccia posseduta: chiede il permesso CORS", () => {
    expect(crossOriginDi("/api/tracks/12/audio")).toBe("anonymous");
    expect(crossOriginDi(`${window.location.origin}/api/tracks/12/audio`)).toBe("anonymous");
  });

  it("preview di terzi: nessuna richiesta di permesso", () => {
    expect(crossOriginDi("https://audio-ssl.itunes.apple.com/preview.m4a")).toBe(null);
    expect(crossOriginDi("https://t4.bcbits.com/stream/abc/mp3-128/1")).toBe(null);
  });
});
