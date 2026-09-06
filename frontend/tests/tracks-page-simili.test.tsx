import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { it as dict } from "@/lib/i18n/it";
import { similarHref } from "@/lib/discovery-dig";

/* Il bottone "Simili" è il primo anello della catena indietro
   libreria -> traccia -> simili -> traccia -> libreria: se non trasporta
   `from`, la traccia ritrovata non ricorda più i filtri da cui si era partiti,
   e il passo indietro successivo riatterra sulla libreria nuda. */

let query = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/tracks",
  useSearchParams: () => query,
}));

const apiGet = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiGet: (...a: unknown[]) => apiGet(...a),
  transitions: () => Promise.resolve([]),
}));

const { default: TrackPage } = await import("@/app/tracks/page");
const { PlayerProvider } = await import("@/lib/player");

const TRACK = {
  id: 5, artist: "Jasmín", title: "Bite The Hand", album: null, genre: null,
  year: null, label: null, bpm: null, camelot_key: null, energy: null,
  duration_seconds: null, status: "imported", source_type: "local",
  has_local_file: true, playlists: [], rating: null,
} as never;

afterEach(cleanup);

async function rendi(search: string, track: unknown = TRACK) {
  apiGet.mockResolvedValue(track);
  query = new URLSearchParams(search);
  render(<PlayerProvider><TrackPage /></PlayerProvider>);
  await waitFor(() => expect(screen.getByText(dict.tracks.similar)).toBeTruthy());
}

const linkSimili = () =>
  screen.getByText(dict.tracks.similar).closest("a") as HTMLAnchorElement;

describe("pagina traccia, il bottone Simili", () => {
  it("porta ai simili l'origine da cui si è arrivati alla traccia", async () => {
    const origine = "/library?genre=Techno&sort=bpm&order=desc";
    await rendi(`id=5&from=${encodeURIComponent(origine)}`);
    expect(linkSimili().getAttribute("href")).toBe(similarHref(5, false, origine));
  });

  it("senza origine punta ai simili e basta", async () => {
    await rendi("id=5");
    expect(linkSimili().getAttribute("href")).toBe(similarHref(5, false));
  });

  it("non compare su una traccia che non possiedi", async () => {
    // I simili partono da un disco che hai: offrirli su un lead prometterebbe
    // un gesto che non è quello pensato.
    apiGet.mockResolvedValue({ ...(TRACK as object), has_local_file: false });
    query = new URLSearchParams("id=5");
    render(<PlayerProvider><TrackPage /></PlayerProvider>);
    await waitFor(() => expect(screen.getByText(dict.tracks.editValues)).toBeTruthy());
    expect(screen.queryByText(dict.tracks.similar)).toBeNull();
  });
});
