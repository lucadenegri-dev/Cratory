import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/* Nel webview di Tauri `target="_blank"` non apre niente: WKWebView chiede al
   delegato una nuova vista, Tauri non ne registra nessuno e il click cade nel
   vuoto — nessuna scheda, nessun errore. Nell'app impacchettata questo rendeva
   inerti TUTTI i link esterni: Spotify, SoundCloud, Discogs, la documentazione,
   la web UI di slskd. Questi test guardano il comportamento del ponte che li
   riporta fuori. */

const apri = vi.fn();
let dentroIlGuscio = true;

vi.mock("@/lib/external-url", async (originale) => {
  const vero = await originale<typeof import("@/lib/external-url")>();
  return { ...vero, isDesktopShell: () => dentroIlGuscio, openExternal: apri };
});

const { ExternalLinkBridge } = await import("@/components/external-link-bridge");

/** jsdom non naviga (stampa "Not implemented"): questo lo evita del tutto e non
 *  interferisce col ponte, che lavora in fase di cattura, molto prima. */
const bloccaNavigazione = (e: Event) => e.preventDefault();

beforeEach(() => {
  dentroIlGuscio = true;
  apri.mockClear();
  document.addEventListener("click", bloccaNavigazione);
});
afterEach(() => {
  document.removeEventListener("click", bloccaNavigazione);
  cleanup();
});

/** L'ancora piu' una spia del `defaultPrevented` letto SUL BERSAGLIO, prima che
 *  `bloccaNavigazione` (in bolla su document, cioe' piu' tardi) lo sporchi:
 *  leggerlo dopo direbbe sempre "fermato" e l'asserzione sarebbe vuota. */
function montaCon(ancora: React.ReactNode) {
  render(<>
    <ExternalLinkBridge />
    {ancora}
  </>);
  const a = screen.getByTestId("ancora");
  let fermato = false;
  a.addEventListener("click", (e) => { fermato = e.defaultPrevented; });
  return { a, fermatoDalPonte: () => fermato };
}

describe("ExternalLinkBridge, nel guscio desktop", () => {
  it("un link esterno finisce nel browser di sistema, non nel webview", () => {
    const { a, fermatoDalPonte } = montaCon(<a data-testid="ancora" href="https://open.spotify.com/track/1" target="_blank" rel="noreferrer">Spotify</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(apri).toHaveBeenCalledWith("https://open.spotify.com/track/1");
    // Se la navigazione non viene fermata, il webview se ne va comunque dalla
    // pagina: aprire fuori non basta, bisogna anche non aprire dentro.
    expect(fermatoDalPonte()).toBe(true);
  });

  it("intercetta anche il click partito da un'icona dentro il link", () => {
    const { a } = montaCon(
      <a data-testid="ancora" href="https://brew.sh" target="_blank" rel="noreferrer">
        <svg data-testid="icona" />
      </a>,
    );
    screen.getByTestId("icona").dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(apri).toHaveBeenCalledWith("https://brew.sh/");
    expect(a).toBeTruthy();
  });

  it("la web UI di slskd e' esterna quanto un sito: e' http su un'altra porta", () => {
    const { a } = montaCon(<a data-testid="ancora" href="http://localhost:5030" target="_blank" rel="noreferrer">slskd</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(apri).toHaveBeenCalledWith("http://localhost:5030/");
  });

  it("un link interno resta dentro l'app", () => {
    const { a } = montaCon(<a data-testid="ancora" href="/tracks?id=12">Traccia</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(apri).not.toHaveBeenCalled();
  });

  it("un download resta un download: non lo si manda al browser di sistema", () => {
    const { a } = montaCon(<a data-testid="ancora" href="https://esempio.invalid/set.m3u8" download="set.m3u8">Esporta</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(apri).not.toHaveBeenCalled();
  });

  it("chi ha gia' fermato l'evento resta fermo", () => {
    // La cattura scende da window a document: un gestore registrato piu' in
    // alto e' l'unico che possa aver gia' deciso quando il ponte guarda.
    const ferma = (e: Event) => e.preventDefault();
    window.addEventListener("click", ferma, true);
    const { a } = montaCon(<a data-testid="ancora" href="https://open.spotify.com/track/1" target="_blank" rel="noreferrer">Spotify</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    window.removeEventListener("click", ferma, true);
    expect(apri).not.toHaveBeenCalled();
  });

  it("Cmd-click e tasto centrale non passano di qui", () => {
    const { a } = montaCon(<a data-testid="ancora" href="https://open.spotify.com/track/1" target="_blank" rel="noreferrer">Spotify</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, metaKey: true }));
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 1 }));
    expect(apri).not.toHaveBeenCalled();
  });
});

describe("ExternalLinkBridge, in un browser normale", () => {
  it("non tocca niente: target=\"_blank\" funziona da se'", () => {
    dentroIlGuscio = false;
    const { a } = montaCon(<a data-testid="ancora" href="https://open.spotify.com/track/1" target="_blank" rel="noreferrer">Spotify</a>);
    a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(apri).not.toHaveBeenCalled();
  });
});

/* Un ponte non montato e' un ponte che non c'e': i test qui sopra sarebbero
   tutti verdi lo stesso, e nel bundle i link tornerebbero inerti. Il layout e'
   l'unico posto che lo monta, e questo e' il pin di quel montaggio. */
describe("il ponte e' montato dal layout", () => {
  const layout = readFileSync(resolve(__dirname, "../app/layout.tsx"), "utf8");

  it("app/layout.tsx lo importa e lo rende", () => {
    expect(layout).toMatch(
      /import\s*\{[^}]*\bExternalLinkBridge\b[^}]*\}\s*from\s*["']@\/components\/external-link-bridge["']/,
    );
    expect(layout).toContain("<ExternalLinkBridge />");
  });
});
