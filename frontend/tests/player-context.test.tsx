import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(() => new Promise(() => {})), // pending: basta a montare la preview
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
  updateTrack: vi.fn(),
}));

import { PlayerProvider, usePlayer, type LocalTrack } from "@/lib/player";

const LIST: LocalTrack[] = [
  { id: 1, title: "One", artist: "A" },
  { id: 2, title: "Two", artist: "A" },
  { id: 3, title: "Three", artist: "A" },
];

function Harness() {
  const p = usePlayer();
  return (
    <div>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[0] }, LIST)}>play-first</button>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[1] }, LIST)}>play-mid</button>
      <button onClick={() => p.play({ kind: "local-track", track: { id: 9, title: "Solo", artist: "B" } })}>play-solo</button>
      <button onClick={() => p.play({ kind: "discovery-preview", item: { key: "x", artist: "Ar", title: "Ti", sourceId: "1", source: "discogs", level: "track", label: "Ti" } })}>play-preview</button>
      <button onClick={() => p.next()}>next</button>
      <button onClick={() => p.prev()}>prev</button>
      <span data-testid="active-id">{p.active?.kind === "local-track" ? p.active.track.id : "-"}</span>
      <span data-testid="has-next">{String(p.hasNext)}</span>
      <span data-testid="has-prev">{String(p.hasPrev)}</span>
    </div>
  );
}

function renderHarness() {
  return render(
    <PlayerProvider>
      <Harness />
    </PlayerProvider>,
  );
}

const click = async (label: string) =>
  act(async () => {
    screen.getByText(label).click();
  });

describe("contesto d'ascolto", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("in mezzo alla lista: prev e next disponibili", async () => {
    renderHarness();
    await click("play-mid");
    expect(screen.getByTestId("active-id").textContent).toBe("2");
    expect(screen.getByTestId("has-prev").textContent).toBe("true");
    expect(screen.getByTestId("has-next").textContent).toBe("true");
  });

  it("next avanza mantenendo il contesto; a fine lista si ferma", async () => {
    renderHarness();
    await click("play-mid");
    await click("next");
    expect(screen.getByTestId("active-id").textContent).toBe("3");
    expect(screen.getByTestId("has-prev").textContent).toBe("true");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
    await click("next"); // no-op al bordo
    expect(screen.getByTestId("active-id").textContent).toBe("3");
  });

  it("prev torna indietro; all'inizio si ferma", async () => {
    renderHarness();
    await click("play-mid");
    await click("prev");
    expect(screen.getByTestId("active-id").textContent).toBe("1");
    expect(screen.getByTestId("has-prev").textContent).toBe("false");
    await click("prev"); // no-op al bordo
    expect(screen.getByTestId("active-id").textContent).toBe("1");
  });

  it("un play senza contesto azzera il contesto", async () => {
    renderHarness();
    await click("play-mid");
    await click("play-solo");
    expect(screen.getByTestId("active-id").textContent).toBe("9");
    expect(screen.getByTestId("has-prev").textContent).toBe("false");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
  });

  it("una preview discovery azzera il contesto", async () => {
    renderHarness();
    await click("play-mid");
    await click("play-preview");
    expect(screen.getByTestId("has-prev").textContent).toBe("false");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
    // tornare a una locale senza contesto non lo resuscita
    await click("play-solo");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
  });

  it("un contesto vuoto equivale a nessun contesto", async () => {
    function EmptyCtx() {
      const p = usePlayer();
      return (
        <div>
          <button onClick={() => p.play({ kind: "local-track", track: LIST[0] }, [])}>play-empty</button>
          <span data-testid="empty-next">{String(p.hasNext)}</span>
        </div>
      );
    }
    render(
      <PlayerProvider>
        <EmptyCtx />
      </PlayerProvider>,
    );
    await act(async () => {
      screen.getByText("play-empty").click();
    });
    expect(screen.getByTestId("empty-next").textContent).toBe("false");
  });
});
