import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(),
}));

import { discoveryPreview } from "@/lib/api";
import { DockedPreviewPlayer } from "@/components/docked-preview-player";
import { PreviewPlayerProvider, usePreviewPlayer } from "@/lib/preview-player";

function Harness() {
  const p = usePreviewPlayer();
  return (
    <div>
      <button onClick={() => p.play({ key: "a", artist: "Artist", title: "Acid Trip", discogsId: 42, level: "track", label: "Acid Trip" })}>
        play-a
      </button>
      <span data-testid="status">{p.status}</span>
    </div>
  );
}

function renderAll() {
  return render(
    <PreviewPlayerProvider>
      <Harness />
      <DockedPreviewPlayer />
    </PreviewPlayerProvider>,
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
      "youtube.com/embed/abcdefghijk",
    );
  });
});
