import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WishlistPage from "@/app/wishlist/page";
import type { DownloadStatus, Track } from "@/lib/api";

afterEach(cleanup);

// Rilievo Important della review: la selezione multipla sopravviveva alle
// azioni di riga che tolgono la traccia dalla vista corrente (es. archivia,
// azzera esito). Il conteggio della barra non corrispondeva più alle
// checkbox visibili e — il danno vero — "Accoda" spediva comunque l'id di
// una traccia appena archiviata, cioè esclusa esplicitamente dall'utente: il
// backend non filtra per archived in fase di accodamento, quindi non c'era
// una seconda rete. Qui si verifica che la selezione si poti quando una riga
// selezionata sparisce dalla vista (per un'azione di riga o per un cambio di
// filtro esplicito).

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/wishlist",
  useSearchParams: () => new URLSearchParams(),
}));

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  slskdStatus: vi.fn(),
  updateTrack: vi.fn(),
  enqueueDownloads: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiGet: mocks.apiGet,
  slskdStatus: mocks.slskdStatus,
  updateTrack: mocks.updateTrack,
  enqueueDownloads: mocks.enqueueDownloads,
}));

const jobsMock = vi.hoisted(() => ({ useJobs: vi.fn() }));
vi.mock("@/components/jobs-provider", () => ({ useJobs: jobsMock.useJobs }));

const track = (over: Partial<Track> = {}): Track => ({
  id: 1, title: "Real Freak", artist: "Marco Faraone", playlists: [],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
  has_local_file: false, archived: false,
  ...over,
} as unknown as Track);

const download = (over: Partial<DownloadStatus> = {}): DownloadStatus => ({
  available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
  needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
  error: null, current_label: null, ...over,
});

beforeEach(() => {
  // reset, non clear: clearAllMocks non svuota la coda di mockResolvedValueOnce,
  // e un test che fallisce prima di consumarla la lascerebbe trapelare nel test
  // successivo (risposta sbagliata alla prima apiGet chiamata).
  vi.resetAllMocks();
  jobsMock.useJobs.mockReturnValue({ download: download(), refresh: vi.fn() });
  mocks.slskdStatus.mockResolvedValue({ web_url: null });
});

async function selectAllRows() {
  const boxes = await screen.findAllByLabelText("Seleziona questa traccia");
  boxes.forEach((b) => fireEvent.click(b));
  return boxes;
}

describe("selezione multipla nella wishlist: potatura quando una riga esce dalla vista", () => {
  it("archiviare una traccia selezionata la toglie dalla selezione, e un successivo accodamento non la include", async () => {
    const t1 = track({ id: 1, title: "Real Freak", artist: "Marco Faraone" });
    const t2 = track({ id: 2, title: "Dark Matter", artist: "Blawan" });
    mocks.apiGet
      .mockResolvedValueOnce({ total: 2, items: [t1, t2] })  // fetch iniziale
      .mockResolvedValueOnce({ total: 1, items: [t2] });     // reload dopo l'archiviazione: t1 e' fuori
    mocks.updateTrack.mockResolvedValue({ ...t1, archived: true });
    mocks.enqueueDownloads.mockResolvedValue({ enqueued: 1, skipped: 0 });

    render(<WishlistPage />);
    await selectAllRows();
    expect(screen.getByText("2 selezionate")).toBeTruthy();

    // Archivia la prima traccia (Marco Faraone) dal menu "..." della sua riga.
    const menus = screen.getAllByLabelText("Altre azioni");
    fireEvent.click(menus[0]);
    fireEvent.click(screen.getByText("Archivia"));
    fireEvent.click(screen.getByRole("button", { name: "Conferma" }));

    await waitFor(() => expect(mocks.updateTrack).toHaveBeenCalledWith(1, { archived: true }));
    // La traccia archiviata e' sparita dalla vista...
    await waitFor(() => expect(screen.queryByText("Marco Faraone — Real Freak")).toBeNull());
    // ...e la selezione si e' potata di conseguenza (non piu' "2 selezionate").
    expect(screen.getByText("1 selezionate")).toBeTruthy();

    fireEvent.click(screen.getByText(/^Accoda/));
    await waitFor(() => expect(mocks.enqueueDownloads).toHaveBeenCalledWith([2]));
  });

  it("la selezione si svuota quando cambia il filtro (tab)", async () => {
    const t1 = track({ id: 1, title: "Real Freak", artist: "Marco Faraone" });
    const t2 = track({ id: 2, title: "Dark Matter", artist: "Blawan" });
    mocks.apiGet.mockResolvedValue({ total: 2, items: [t1, t2] });

    render(<WishlistPage />);
    await selectAllRows();
    expect(screen.getByText("2 selezionate")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: /Mai tentate/ }));

    expect(screen.queryByText(/selezionate/)).toBeNull();
  });
});
