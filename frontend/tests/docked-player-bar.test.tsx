import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(),
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
  updateTrack: vi.fn(),
}));

import { DockedPlayer } from "@/components/docked-player";
import { PlayerProvider, usePlayer, type LocalTrack } from "@/lib/player";

const LIST: LocalTrack[] = [
  { id: 5, title: "First", artist: "A" },
  { id: 6, title: "Second", artist: "A" },
];

function Harness() {
  const p = usePlayer();
  return (
    <div>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[0] }, LIST)}>play-ctx</button>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[0] })}>play-solo</button>
      <span data-testid="active-id">{p.active?.kind === "local-track" ? p.active.track.id : "-"}</span>
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

describe("barra player", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("con contesto: a fine traccia avanza alla successiva", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("active-id").textContent).toBe("6");
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/6/audio");
  });

  it("senza contesto: a fine traccia si ferma sulla stessa", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-solo").click();
    });
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("active-id").textContent).toBe("5");
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
  });

  it("errore audio: messaggio, NIENTE salto alla traccia dopo", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    await act(async () => {
      fireEvent.error(screen.getByTestId("local-audio"));
    });
    // il salto a catena maschererebbe file rotti: si resta sull'errore
    expect(screen.getByTestId("active-id").textContent).toBe("5");
    expect(screen.queryByTestId("local-audio")).toBeNull();
    expect(screen.getByText(/browser/i)).toBeTruthy();
  });

  it("prev/next del trasporto cablati al provider", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    await act(async () => {
      screen.getByLabelText("Traccia successiva").click();
    });
    expect(screen.getByTestId("active-id").textContent).toBe("6");
    await act(async () => {
      screen.getByLabelText("Traccia precedente").click();
    });
    expect(screen.getByTestId("active-id").textContent).toBe("5");
  });

  it("a player chiuso la CSS var dell'altezza torna a 0px", async () => {
    const { unmount } = renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    unmount();
    expect(document.documentElement.style.getPropertyValue("--player-bar-height")).toBe("0px");
  });
});
