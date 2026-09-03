import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ServiceStatus, SlskdDaemonStatus, SlskdStatus, SoundCloudStatus } from "@/lib/api";

const slskdStatusFn = vi.fn<() => Promise<SlskdStatus>>();
const slskdConnect = vi.fn();
const slskdDisconnect = vi.fn();
const soundcloudStatusFn = vi.fn<() => Promise<SoundCloudStatus>>();
const setSoundcloudUsername = vi.fn();
const runFingerprint = vi.fn();
// Il demone (accendi/spegni il processo slskd) va mockato a parte dal login
// soulseek sopra: senza, cadono sul client HTTP vero, il cui fetch fallisce
// nell'ambiente di test e viene inghiottito dal .catch del componente — il
// blocco del demone resta `null` e non renderizza mai (nessuna copertura
// reale, anche con un'etichetta sbagliata i test resterebbero verdi).
const daemonStatusFn = vi.fn<() => Promise<SlskdDaemonStatus>>();
const daemonStart = vi.fn();
const daemonStop = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  slskdStatus: (...a: unknown[]) => slskdStatusFn(...(a as [])),
  slskdConnect: (...a: unknown[]) => slskdConnect(...(a as [])),
  slskdDisconnect: (...a: unknown[]) => slskdDisconnect(...(a as [])),
  soundcloudStatus: (...a: unknown[]) => soundcloudStatusFn(...(a as [])),
  setSoundcloudUsername: (...a: unknown[]) => setSoundcloudUsername(...(a as [])),
  daemonStatus: (...a: unknown[]) => daemonStatusFn(...(a as [])),
  daemonStart: (...a: unknown[]) => daemonStart(...(a as [])),
  daemonStop: (...a: unknown[]) => daemonStop(...(a as [])),
}));
vi.mock("@/lib/organize/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  runFingerprint: (...a: unknown[]) => runFingerprint(...(a as [])),
}));

const { ServicesList } = await import("@/components/settings/services-list");

function svc(over: Partial<ServiceStatus>): ServiceStatus {
  return {
    key: "x", name: "X", category: "Cat", configured: true, connected: null,
    detail: "d", env: [], optional_env: [], optional_ok: null,
    docs: "https://example.com", ...over,
  } as ServiceStatus;
}

const SEVEN: ServiceStatus[] = [
  svc({ key: "spotify", name: "Spotify", connected: false }),
  svc({ key: "anthropic", name: "Anthropic — AI", env: ["ANTHROPIC_API_KEY"] }),
  svc({ key: "discogs", name: "Discogs", optional_env: ["DISCOGS_TOKEN"], optional_ok: false }),
  svc({ key: "musicbrainz", name: "MusicBrainz" }),
  svc({ key: "acoustid", name: "AcoustID / Chromaprint" }),
  svc({ key: "slskd", name: "slskd (Soulseek)" }),
  svc({ key: "soundcloud", name: "SoundCloud" }),
];

beforeEach(() => {
  slskdStatusFn.mockResolvedValue({
    configured: true, reachable: true, is_connected: false, is_logged_in: false,
    is_connecting: false, is_transitioning: false, state: null, username: null,
    unauthorized: false, web_url: null,
  });
  soundcloudStatusFn.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "luca" });
  daemonStatusFn.mockResolvedValue({ reachable: false, owned: null, pid: null, installed: true, configured: true, username: null });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("ServicesList", () => {
  it("rende una riga per ogni servizio", async () => {
    render(<ServicesList services={SEVEN} spotify={null} />);
    for (const s of SEVEN) expect(screen.getByText(s.name)).toBeTruthy();
  });

  it("token opzionale mancante → 'token consigliato', non 'non configurata'", async () => {
    render(<ServicesList services={SEVEN} spotify={null} />);
    expect(screen.getByText(/token consigliato|token recommended/i)).toBeTruthy();
    expect(screen.queryByText(/non configurata|not configured/i)).toBeNull();
  });

  /* Il bottone Connetti di slskd non sta piu' qui: la lista monta
     <SlskdRow />, che copre l'intero percorso. Il test del clic che chiama
     slskdConnect e' in tests/slskd-row.test.tsx. */

  it("soundcloud: salva l'username col valore ripulito", async () => {
    setSoundcloudUsername.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "nuovo-nome" });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const input = await screen.findByDisplayValue("luca");
    fireEvent.change(input, { target: { value: "  nuovo-nome " } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(setSoundcloudUsername).toHaveBeenCalledWith("nuovo-nome"));
  });

  /* Segnalazione reale: "inserisco l'username SoundCloud, premo Salva e non
     succede niente". Il salvataggio riusciva — l'username finiva davvero in
     AppState — ma nella riga non cambiava un pixel: il campo conteneva gia'
     quello che l'utente aveva scritto, e il badge di stato della riga viene
     da yt-dlp, non dall'username. Un successo indistinguibile da un bottone
     morto. Il resto delle Impostazioni la conferma la dava gia'
     (config-card mostra `savedLabel`): qui mancava e basta. */
  it("soundcloud: il salvataggio riuscito si vede", async () => {
    setSoundcloudUsername.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "nuovo-nome" });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const input = await screen.findByDisplayValue("luca");
    fireEvent.change(input, { target: { value: "nuovo-nome" } });
    expect(screen.queryByText(/salvato|saved/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(screen.getByText(/salvato|saved/i)).toBeTruthy());
  });

  it("soundcloud: il salvataggio fallito non si traveste da riuscito", async () => {
    setSoundcloudUsername.mockRejectedValue(new Error("backend non raggiungibile"));
    render(<ServicesList services={SEVEN} spotify={null} />);
    const input = await screen.findByDisplayValue("luca");
    fireEvent.change(input, { target: { value: "nuovo-nome" } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(screen.getByText(/backend non raggiungibile/)).toBeTruthy());
    expect(screen.queryByText(/salvato|saved/i)).toBeNull();
  });

  it("soundcloud: Invio nel campo salva, non ricarica la pagina", async () => {
    /* Il campo era fuori da un form: chi scrive un username e preme Invio,
       che e' il gesto naturale, non salvava nulla — l'altra meta' del
       "non succede niente". */
    setSoundcloudUsername.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "da-invio" });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const input = await screen.findByDisplayValue("luca");
    fireEvent.change(input, { target: { value: "da-invio" } });
    const form = input.closest("form");
    expect(form).toBeTruthy();
    fireEvent.submit(form!);
    await waitFor(() => expect(setSoundcloudUsername).toHaveBeenCalledWith("da-invio"));
  });

  it("acoustid configurato: 'Identifica ora' chiama runFingerprint", async () => {
    runFingerprint.mockResolvedValue({ configured: true, identified: 1, below_threshold: 0, not_found: 0, errors: 0, total: 1 });
    render(<ServicesList services={SEVEN} spotify={null} />);
    fireEvent.click(screen.getByRole("button", { name: /identifica ora|identify now/i }));
    await waitFor(() => expect(runFingerprint).toHaveBeenCalledTimes(1));
  });

  it("demone non raggiungibile: il bottone porta l'etichetta breve di Impostazioni, non quella del wizard", async () => {
    // Regressione reale già vista: scambiare qui l'etichetta con quella del
    // wizard ("Scarica, configura e avvia") promette un download e una
    // scrittura di configurazione che in questa pagina non avvengono.
    daemonStatusFn.mockResolvedValue({ reachable: false, owned: null, pid: null, installed: true, configured: true, username: null });
    render(<ServicesList services={SEVEN} spotify={null} />);
    expect(await screen.findByRole("button", { name: "Avvia" })).toBeTruthy();
    expect(screen.queryByText(/scarica, configura e avvia|download, configure and start/i)).toBeNull();
  });

  it("demone raggiungibile e avviato da noi: c'è il bottone Ferma e chiama daemonStop", async () => {
    daemonStatusFn.mockResolvedValue({ reachable: true, owned: true, pid: 42, installed: true, configured: true, username: null });
    daemonStop.mockResolvedValue({ reachable: false, owned: null, pid: null, installed: true, configured: true, username: null });
    render(<ServicesList services={SEVEN} spotify={null} />);
    expect(await screen.findByText("In esecuzione")).toBeTruthy();
    const stop = screen.getByRole("button", { name: /ferma|stop/i });
    fireEvent.click(stop);
    await waitFor(() => expect(daemonStop).toHaveBeenCalledTimes(1));
  });

  it("demone raggiungibile ma acceso da altri: niente bottone Ferma, etichetta dedicata", async () => {
    daemonStatusFn.mockResolvedValue({ reachable: true, owned: false, pid: null, installed: true, configured: true, username: null });
    render(<ServicesList services={SEVEN} spotify={null} />);
    expect(await screen.findByText(/avviato fuori da cratory|started outside cratory/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ferma|stop/i })).toBeNull();
  });

  it("demone raggiungibile, proprietà non rilevabile: niente bottone Ferma, etichetta dedicata", async () => {
    daemonStatusFn.mockResolvedValue({ reachable: true, owned: null, pid: null, installed: true, configured: true, username: null });
    render(<ServicesList services={SEVEN} spotify={null} />);
    expect(await screen.findByText(/non è possibile stabilire|can't tell/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ferma|stop/i })).toBeNull();
  });
});
