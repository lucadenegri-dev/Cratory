import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";
import { HEART } from "@/components/dashboard/ascii-atmosphere";

/* L'easter egg DJ GOODGIRL (spec 2026-09-04) si accende dalla Home leggendo
   l'username SoundCloud. Qui l'API è finta: conta che la persona arrivi ai
   tre componenti d'arte insieme, e che prima della risposta non ci sia
   niente da far lampeggiare. */

const soundcloudStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  apiGet: (path: string) => {
    if (path === "/api/stats") return Promise.resolve({ total_tracks: 10, with_local_file: 4 });
    return Promise.resolve([]);
  },
  getPipeline: () => Promise.resolve(null),
  listImportedPlaylists: () => Promise.resolve([]),
  soundcloudStatus: () => soundcloudStatus(),
}));

vi.mock("@/lib/player", () => ({
  usePlayer: () => ({ audible: false, play: vi.fn() }),
}));

vi.mock("@/lib/audio-analyser", () => ({
  primeOnFirstGesture: vi.fn(),
  readLevels: () => null,
  bandEdgeHz: () => 0,
}));

const status = (username: string | null) => ({ available: true, ytdlp_version: null, username });

const hasHearts = (root: HTMLElement) =>
  [...root.querySelectorAll("span")].some((s) => s.textContent === HEART);

describe("Home: la persona del frontespizio", () => {
  /* Niente mockReset/mockClear fra un test e l'altro: con vitest 4, svuotare i
     risultati del mock fa riaffiorare come errore del test il rifiuto (già
     gestito dalla Home) del caso "backend giù". Non serve comunque: ogni test
     imposta per intero la propria risposta con mockResolvedValue/RejectedValue. */
  afterEach(cleanup);

  it("con xgiorgix dice DJ Goodgirl, la DJ è riccia e nell'aria ci sono cuori", async () => {
    soundcloudStatus.mockResolvedValue(status("xgiorgix"));
    const { container } = render(<Home />);
    // Niente lampeggio: finché la persona non è nota, la scritta non c'è.
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();

    expect(await screen.findByRole("heading", { level: 1, name: "DJ Goodgirl" })).toBeTruthy();
    await waitFor(() => expect(container.textContent).toContain("/(oo)\\"));
    expect(container.textContent).not.toContain("_(oo)_");
    expect(hasHearts(container)).toBe(true);
  });

  it("con un altro username resta Cratory, senza cuori", async () => {
    soundcloudStatus.mockResolvedValue(status("giorgia"));
    const { container } = render(<Home />);
    expect(await screen.findByRole("heading", { level: 1, name: "Cratory" })).toBeTruthy();
    await waitFor(() => expect(container.textContent).toContain("_(oo)_"));
    expect(container.textContent).not.toContain("/(oo)\\");
    expect(hasHearts(container)).toBe(false);
  });

  it("se lo stato SoundCloud non arriva, resta Cratory", async () => {
    soundcloudStatus.mockRejectedValue(new Error("backend giù"));
    render(<Home />);
    expect(await screen.findByRole("heading", { level: 1, name: "Cratory" })).toBeTruthy();
  });
});
