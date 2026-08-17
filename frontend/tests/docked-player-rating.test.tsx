import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  // Il dock carica BPM/tonalità/genere dalla scheda (GET /api/tracks/{id}):
  // una promise mai risolta = dock senza riga metadati, il caso base dei test.
  apiGet: vi.fn(() => new Promise(() => {})),
  discoveryPreview: vi.fn(),
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
  updateTrack: vi.fn(),
}));

import { apiGet, discoveryPreview } from "@/lib/api";
import { DockedPlayer } from "@/components/docked-player";
import { PlayerProvider, usePlayer } from "@/lib/player";

function Harness() {
  const p = usePlayer();
  return (
    <div>
      <button
        onClick={() =>
          p.play({ kind: "local-track", track: { id: 5, title: "T", artist: "A", rating: 2 } })
        }
      >
        play-local
      </button>
      <button
        onClick={() =>
          p.play({
            kind: "discovery-preview",
            item: { key: "a", artist: "Artist", title: "Acid Trip", sourceId: "42", source: "discogs", level: "track", label: "Acid Trip" },
          })
        }
      >
        play-preview
      </button>
    </div>
  );
}

function renderAll() {
  return render(
    <PlayerProvider>
      <Harness />
      <DockedPlayer />
    </PlayerProvider>,
  );
}

describe("voto dal player docked", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "itunes", audio_url: "http://p", youtube_video_id: null, source_url: null, matched_title: "Acid Trip",
    });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("con una traccia locale in riproduzione il dock mostra il rombo del voto", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-local").click();
    });
    expect(screen.getByLabelText("Voto")).toBeTruthy();
  });

  /* La riga BPM/tonalità/genere arriva dalla scheda: compare quando la GET
     risolve, e ogni cella si rende solo se il dato c'è. */
  it("con la scheda caricata il dock mostra BPM, tonalità e genere", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      bpm: 126.5, camelot_key: "8A", genre: "Techno",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-local").click();
    });
    expect(screen.getByText("126.5")).toBeTruthy();
    expect(screen.getByText("8A")).toBeTruthy();
    expect(screen.getByText("Techno")).toBeTruthy();
    expect(apiGet).toHaveBeenCalledWith("/api/tracks/5");
  });

  it("senza BPM né tonalità la riga mostra solo il genere, niente celle vuote", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      bpm: null, camelot_key: null, genre: "Ambient",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-local").click();
    });
    expect(screen.getByText("Ambient")).toBeTruthy();
    expect(screen.queryByText("BPM")).toBeNull();
  });

  it("con una preview discovery il rombo non c'e'", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-preview").click();
    });
    expect(screen.queryByLabelText("Voto")).toBeNull();
  });
});
