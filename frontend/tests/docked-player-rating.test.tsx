import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(),
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
  updateTrack: vi.fn(),
}));

import { discoveryPreview } from "@/lib/api";
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

  it("con una preview discovery il rombo non c'e'", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-preview").click();
    });
    expect(screen.queryByLabelText("Voto")).toBeNull();
  });
});
