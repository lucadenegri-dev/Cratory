import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(),
  // Il dock renderizza sempre una miniatura (TrackCover→trackCoverSrc) e, per le
  // tracce locali, un <audio src={trackAudioUrl}>; l'ADD chiama save-for-later.
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
}));

import { discoveryPreview } from "@/lib/api";
import { DockedPlayer } from "@/components/docked-player";
import { PlayerProvider, usePlayer } from "@/lib/player";

function Harness() {
  const p = usePlayer();
  return (
    <div>
      <button onClick={() => p.play({ kind: "discovery-preview", item: { key: "a", artist: "Artist", title: "Acid Trip", discogsId: 42, level: "track", label: "Acid Trip" } })}>
        play-a
      </button>
      <button onClick={() => p.play({ kind: "discovery-preview", item: { key: "b", artist: "Artist", title: "Other", discogsId: 42, level: "track", label: "Other" } })}>
        play-b
      </button>
      <span data-testid="status">{p.status}</span>
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

describe("preview player", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("resolves an itunes preview and shows an audio element", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "itunes", audio_url: "http://p", youtube_video_id: null, source_url: "http://v", matched_title: "Acid Trip",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("playing"));
    expect(screen.getByTestId("preview-audio").getAttribute("src")).toBe("http://p");
  });

  it("shows unavailable when kind is none", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "none", audio_url: null, youtube_video_id: null, source_url: null, matched_title: null,
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unavailable"));
  });

  it("renders a youtube iframe on youtube kind", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "youtube", audio_url: null, youtube_video_id: "abcdefghijk", source_url: "http://y", matched_title: "Artist - Acid Trip",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("preview-iframe")).toBeTruthy());
    expect(screen.getByTestId("preview-iframe").getAttribute("src")).toContain(
      "youtube-nocookie.com/embed/abcdefghijk",
    );
  });

  it("a newer play supersedes a slower older in-flight resolution", async () => {
    let resolveA: (v: unknown) => void = () => {};
    const pending = new Promise((r) => {
      resolveA = r as (v: unknown) => void;
    });
    (discoveryPreview as ReturnType<typeof vi.fn>)
      .mockReturnValueOnce(pending) // play-a: stays pending
      .mockResolvedValueOnce({
        kind: "youtube", audio_url: null, youtube_video_id: "bbbbbbbbbbb", source_url: "http://y", matched_title: "Other",
      }); // play-b: resolves immediately

    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await act(async () => {
      screen.getByText("play-b").click();
    });
    await waitFor(() => expect(screen.getByTestId("preview-iframe")).toBeTruthy());

    // Now resolve the older (play-a) request LATE — it must NOT override play-b's youtube state.
    await act(async () => {
      resolveA({ kind: "itunes", audio_url: "http://p", youtube_video_id: null, source_url: "http://v", matched_title: "Acid Trip" });
    });

    expect(screen.getByTestId("preview-iframe")).toBeTruthy();
    expect(screen.queryByTestId("preview-audio")).toBeNull();
    expect(screen.getByTestId("status").textContent).toBe("playing");
  });
});
