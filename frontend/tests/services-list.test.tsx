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
    web_url: null,
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

  it("slskd: il bottone Connetti chiama slskdConnect", async () => {
    slskdConnect.mockResolvedValue({
      configured: true, reachable: true, is_connected: true, is_logged_in: true,
      is_connecting: false, is_transitioning: false, state: null, username: "u",
      web_url: null,
    });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const btn = await screen.findByRole("button", { name: /connetti|connect/i });
    fireEvent.click(btn);
    await waitFor(() => expect(slskdConnect).toHaveBeenCalledTimes(1));
  });

  it("soundcloud: salva l'username col valore ripulito", async () => {
    setSoundcloudUsername.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "nuovo-nome" });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const input = await screen.findByDisplayValue("luca");
    fireEvent.change(input, { target: { value: "  nuovo-nome " } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(setSoundcloudUsername).toHaveBeenCalledWith("nuovo-nome"));
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
