import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SoulseekSearchModal } from "@/components/soulseek-search-modal";
import type { SoulseekSearchFile } from "@/lib/api";

afterEach(cleanup);

const file = (over: Partial<SoulseekSearchFile> = {}): SoulseekSearchFile => ({
  username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac", size: 30_000_000,
  bitrate: null, length: 294, format: null, has_free_slot: true, queue_length: 0,
  upload_speed: null, score: 120, confidence: 0.9, auto_ok: true, ...over,
});

const mocks = vi.hoisted(() => ({
  soulseekSearch: vi.fn(),
  downloadReview: vi.fn(),
  downloadTrack: vi.fn(),
}));

// Si sostituiscono solo le funzioni usate dal modal; il resto del modulo resta vero
// (fmtDuration/fmtSize e i tipi servono davvero).
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  soulseekSearch: mocks.soulseekSearch,
  downloadReview: mocks.downloadReview,
  downloadTrack: mocks.downloadTrack,
}));

const target = { track_id: 1, artist: "Aphex Twin", title: "Xtal" };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.downloadReview.mockResolvedValue({
    expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 },
    downloaded: null, reason: null,
  });
  mocks.soulseekSearch.mockResolvedValue({
    variants: ["Aphex Twin Xtal", "Aphex Twin"],
    results: [file(), file({ username: "user2", filename: "b1 rip.mp3", bitrate: 128,
                             score: 40, confidence: 0.3, auto_ok: false })],
  });
});

describe("SoulseekSearchModal", () => {
  it("all'apertura lancia la ricerca con la query precompilata", async () => {
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenCalledWith("Aphex Twin Xtal", 1));
    expect(await screen.findByText("Xtal.flac")).toBeTruthy();
    expect(screen.getByText("b1 rip.mp3")).toBeTruthy();  // nessun filtro a soglia
    expect(screen.getByText("affidabile")).toBeTruthy();  // badge solo sul candidato auto_ok
  });

  it("le varianti compilano il campo e rilanciano la ricerca", async () => {
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getByRole("button", { name: "Aphex Twin" }));
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenLastCalledWith("Aphex Twin", 1));
    expect((screen.getByLabelText("Query di ricerca Soulseek") as HTMLInputElement).value)
      .toBe("Aphex Twin");
  });

  it("«Scarica questo» chiama downloadTrack col candidato giusto e poi onPicked", async () => {
    mocks.downloadTrack.mockResolvedValue({});
    const onPicked = vi.fn();
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={onPicked} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getAllByText("Scarica questo")[0]);
    await waitFor(() => expect(mocks.downloadTrack).toHaveBeenCalledWith(1,
      expect.objectContaining({ username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac" })));
    await waitFor(() => expect(onPicked).toHaveBeenCalled());
  });

  it("mostra il delta durata rispetto all'attesa", async () => {
    mocks.soulseekSearch.mockResolvedValue({
      variants: [], results: [file({ length: 297 })],
    });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    // durata attesa 294 (dal review), file 297 -> "+3s vs atteso"
    expect(await screen.findByText(/\+3s/)).toBeTruthy();
  });

  it("blocco Tieni/Scarta presente quando c'e' un file dubbio", async () => {
    mocks.downloadReview.mockResolvedValue({
      expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 },
      downloaded: { path: "/inbox/x.mp3", name: "x.mp3", format: "mp3", bitrate: 320,
                    duration_seconds: 250, size: 9_000_000 },
      reason: "durata non corrisponde",
    });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    expect(await screen.findByText("Tieni comunque")).toBeTruthy();
    expect(screen.getByText("Scarta")).toBeTruthy();
  });
});
