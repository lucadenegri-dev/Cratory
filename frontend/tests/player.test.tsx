import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  // Il dock carica BPM/tonalità/genere dalla scheda (GET /api/tracks/{id}):
  // una promise mai risolta = dock senza riga metadati, il caso base dei test.
  apiGet: vi.fn(() => new Promise(() => {})),
  discoveryPreview: vi.fn(),
  // Il dock renderizza sempre una miniatura (TrackCover→trackCoverSrc) e, per le
  // tracce locali, un <audio src={trackAudioUrl}>; l'ADD chiama save-for-later.
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
      <button onClick={() => p.play({ kind: "discovery-preview", item: { key: "a", artist: "Artist", title: "Acid Trip", sourceId: "42", source: "discogs", level: "track", label: "Acid Trip" } })}>
        play-a
      </button>
      <button onClick={() => p.play({ kind: "discovery-preview", item: { key: "b", artist: "Artist", title: "Other", sourceId: "42", source: "discogs", level: "track", label: "Other" } })}>
        play-b
      </button>
      <button onClick={() => p.play({ kind: "local-track", track: { id: 5, title: "T", artist: "A" } })}>
        play-local
      </button>
      <button onClick={() => p.stop()}>stop</button>
      <span data-testid="status">{p.status}</span>
      <span data-testid="audible">{String(p.audible)}</span>
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
    const src = screen.getByTestId("preview-iframe").getAttribute("src") ?? "";
    // Passa dal backend, che serve una pagina contenente l'iframe di YouTube.
    expect(src).toContain("/api/discovery/preview/youtube/abcdefghijk");
    // E NON punta a YouTube direttamente: e' la causa dell'"Errore 153 -
    // configurazione del video player" nel guscio desktop, dove la pagina sta
    // su tauri://localhost e non produce un `Referer` che YouTube accetti.
    expect(src).not.toContain("youtube-nocookie.com");
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

/* `audible` è lo stato che la Home usa per animare la consolle: deve seguire il
   suono che esce davvero, non ciò che è caricato nel dock. */
describe("audible: il suono che esce davvero", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("parte falso e resta falso finché l'elemento audio non suona", async () => {
    renderAll();
    expect(screen.getByTestId("audible").textContent).toBe("false");
    await act(async () => {
      screen.getByText("play-local").click();
    });
    // Il dock ha montato l'audio (status=playing) ma nessun evento è ancora partito.
    expect(screen.getByTestId("status").textContent).toBe("playing");
    expect(screen.getByTestId("audible").textContent).toBe("false");
  });

  it("segue play/pause/ended dell'elemento audio locale", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-local").click();
    });
    const audio = screen.getByTestId("local-audio");

    await act(async () => {
      fireEvent.play(audio);
    });
    expect(screen.getByTestId("audible").textContent).toBe("true");

    await act(async () => {
      fireEvent.pause(audio);
    });
    expect(screen.getByTestId("audible").textContent).toBe("false");

    await act(async () => {
      fireEvent.play(audio);
      fireEvent.ended(audio);
    });
    expect(screen.getByTestId("audible").textContent).toBe("false");
  });

  it("segue play/pause anche sull'audio della preview discovery", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "itunes", audio_url: "http://p", youtube_video_id: null, source_url: "http://v", matched_title: "Acid Trip",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("preview-audio")).toBeTruthy());

    await act(async () => {
      fireEvent.play(screen.getByTestId("preview-audio"));
    });
    expect(screen.getByTestId("audible").textContent).toBe("true");

    await act(async () => {
      fireEvent.pause(screen.getByTestId("preview-audio"));
    });
    expect(screen.getByTestId("audible").textContent).toBe("false");
  });

  it("l'iframe YouTube conta come audibile: non espone eventi, ma è in autoplay", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "youtube", audio_url: null, youtube_video_id: "abcdefghijk", source_url: "http://y", matched_title: "Artist - Acid Trip",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("preview-iframe")).toBeTruthy());
    expect(screen.getByTestId("audible").textContent).toBe("true");
  });

  it("chiudere il dock (stop) azzera audible", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-local").click();
    });
    await act(async () => {
      fireEvent.play(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("audible").textContent).toBe("true");

    await act(async () => {
      screen.getByText("stop").click();
    });
    expect(screen.getByTestId("audible").textContent).toBe("false");
  });

  it("cambiare traccia azzera audible finché la nuova non parte", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-local").click();
    });
    await act(async () => {
      fireEvent.play(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("audible").textContent).toBe("true");

    (discoveryPreview as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    await act(async () => {
      screen.getByText("play-a").click();
    });
    expect(screen.getByTestId("audible").textContent).toBe("false");
  });
});
