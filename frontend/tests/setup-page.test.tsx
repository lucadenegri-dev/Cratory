import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const replace = vi.fn();
// Il wizard legge la query string per sapere com'e' andato l'OAuth Spotify:
// il callback del backend ci riporta qui, non piu' su /settings (dove il
// SetupGate rimbalzerebbe indietro, wizard da capo e nessuna spiegazione).
let query = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/setup",
  useSearchParams: () => query,
}));

// Il mock deve esporre OGNI export usato dalla pagina: vitest solleva
// "No 'X' export is defined on the mock" al primo accesso mancante
// (stesso pattern di tests/credential-field.test.tsx).
const setSetupCompleted = vi.fn();
// `getProbe` serve alla pagina per sapere se il passo dei prerequisiti ha
// ancora qualcosa da chiedere (vedi lib/setup-steps.ts). Qui risponde con due
// componenti che NON vengono dal bundle: il wizard resta a cinque passi, che è
// la forma in cui questi test lo conoscono.
const getProbe = vi.fn().mockResolvedValue({
  platform: "darwin-arm64",
  components: [
    { key: "ffmpeg", present: true, source: "path" },
    { key: "fpcalc", present: false, source: null },
  ],
});
// Il resto del modulo passa dall'originale (stesso schema di
// tests/services-list.test.tsx): tornando dall'OAuth il wizard monta davvero
// il passo Servizi, che di `@/lib/api` usa molto piu' di queste tre — e un
// mock a elenco chiuso fallirebbe al primo export non previsto. Le chiamate
// vere non escono: il fetch fallisce in ambiente di test e i componenti lo
// inghiottono nei loro `.catch`, che e' il caso "backend giu'" che gia'
// gestiscono.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  setSetupCompleted: (...a: unknown[]) => setSetupCompleted(...a),
  getProbe: (...a: unknown[]) => getProbe(...a),
}));

const { default: SetupPage } = await import("@/app/setup/page");

describe("SetupPage", () => {
  beforeEach(() => { replace.mockClear(); setSetupCompleted.mockReset(); query = new URLSearchParams(); });
  afterEach(cleanup);

  it("scrittura riuscita: porta a /", async () => {
    setSetupCompleted.mockResolvedValue({ completed: true });
    render(<SetupPage />);
    fireEvent.click(screen.getByText("Salta la configurazione"));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("scrittura fallita: resta sul wizard, mostra l'errore, non naviga", async () => {
    setSetupCompleted.mockRejectedValue(new Error("backend non raggiungibile"));
    render(<SetupPage />);
    fireEvent.click(screen.getByText("Salta la configurazione"));
    await waitFor(() => expect(screen.getByText(/backend non raggiungibile/)).toBeTruthy());
    expect(replace).not.toHaveBeenCalled();
  });

  it("il sottotitolo conta i passi veri, non un numero scritto a mano", async () => {
    /* Diceva "Sei passi" molto dopo che erano diventati cinque, e ancora
       quando nel bundle erano quattro. Il numero ora viene da chi i passi li
       compone: qui il probe dice `path`, quindi cinque. */
    setSetupCompleted.mockResolvedValue({ completed: true });
    render(<SetupPage />);
    await waitFor(() => expect(screen.getByText(/5 passi|5 steps/)).toBeTruthy());
    expect(screen.queryByText(/Sei passi|Six steps/)).toBeNull();
  });

  /* Segnalazione reale: nel wizard si preme Connetti, su Spotify si preme
     Accetta, e non succede niente. Il collegamento avveniva davvero — il
     token veniva scambiato — ma il callback riportava sempre su
     `http://localhost:3000/settings`: nel bundle desktop non c'e' nessuno a
     quell'indirizzo, e anche dove c'e' il SetupGate rimbalza subito su /setup
     perche' il wizard non e' concluso. In tutti i casi l'esito non lo vedeva
     nessuno. Ora si torna QUI, e qui l'esito si legge. */
  it("tornando dall'OAuth il wizard dice che Spotify e' collegato", async () => {
    query = new URLSearchParams("spotify=connected");
    render(<SetupPage />);
    expect(screen.getByText(/Account Spotify collegato/)).toBeTruthy();
  });

  it("tornando dall'OAuth fallito il wizard dice perche'", async () => {
    query = new URLSearchParams("spotify=error&detail=access_denied");
    render(<SetupPage />);
    expect(screen.getByText(/Login Spotify fallito \(access_denied\)/)).toBeTruthy();
  });

  it("tornando dall'OAuth riapre il passo Servizi, non il primo", async () => {
    /* E' un caricamento vero, non una navigazione client: senza questo il
       wizard riparte da "Benvenuto" e l'utente deve ritrovarsi da solo il
       passo da cui era partito. */
    query = new URLSearchParams("spotify=connected");
    render(<SetupPage />);
    await waitFor(() => expect(screen.getByText("Servizi esterni")).toBeTruthy());
    expect(screen.queryByText("Benvenuto in Cratory")).toBeNull();
  });

  it("senza ritorno dall'OAuth si parte dal primo passo, come sempre", async () => {
    render(<SetupPage />);
    await waitFor(() => expect(screen.getByText("Benvenuto in Cratory")).toBeTruthy());
    expect(screen.queryByText(/Account Spotify collegato/)).toBeNull();
  });

  it("nel bundle il sottotitolo dice quattro", async () => {
    getProbe.mockResolvedValueOnce({
      platform: "darwin-arm64",
      components: [
        { key: "ffmpeg", present: true, source: "bundle" },
        { key: "fpcalc", present: true, source: "bundle" },
      ],
    });
    render(<SetupPage />);
    await waitFor(() => expect(screen.getByText(/4 passi|4 steps/)).toBeTruthy());
  });
});

