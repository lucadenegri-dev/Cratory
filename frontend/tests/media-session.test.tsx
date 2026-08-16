import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerTransport } from "@/components/player-transport";

/* jsdom non ha né mediaSession né MediaMetadata: stub minimi. */
class FakeMediaMetadata {
  constructor(public init: { title?: string; artist?: string; artwork?: { src: string }[] }) {}
}

type Handler = (() => void) | null;

function installMediaSession() {
  const handlers = new Map<string, Handler>();
  const ms = {
    metadata: null as FakeMediaMetadata | null,
    setActionHandler: vi.fn((action: string, h: Handler) => handlers.set(action, h)),
  };
  Object.defineProperty(navigator, "mediaSession", { configurable: true, value: ms });
  vi.stubGlobal("MediaMetadata", FakeMediaMetadata);
  return { ms, handlers };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  // @ts-expect-error: rimozione dello stub per il test successivo
  delete navigator.mediaSession;
});

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
});

const META = { title: "Acid Trip", artist: "Artist", artworkUrl: "http://art" };

describe("Media Session", () => {
  it("pubblica i metadata e gli handler play/pause", () => {
    const { ms, handlers } = installMediaSession();
    render(<PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />);
    const meta = ms.metadata as FakeMediaMetadata;
    expect(meta.init.title).toBe("Acid Trip");
    expect(meta.init.artist).toBe("Artist");
    expect(meta.init.artwork).toEqual([{ src: "http://art" }]);
    expect(typeof handlers.get("play")).toBe("function");
    expect(typeof handlers.get("pause")).toBe("function");
    // senza contesto, prev/next sono esplicitamente rimossi
    expect(handlers.get("previoustrack")).toBeNull();
    expect(handlers.get("nexttrack")).toBeNull();
  });

  it("con contesto registra previoustrack/nexttrack sui bordi disponibili", () => {
    const { handlers } = installMediaSession();
    const onPrev = vi.fn();
    const onNext = vi.fn();
    render(
      <PlayerTransport
        src="/a"
        testId="local-audio"
        onAudible={() => {}}
        mediaMeta={META}
        prevNext={{ hasPrev: false, hasNext: true, onPrev, onNext }}
      />,
    );
    expect(handlers.get("previoustrack")).toBeNull(); // bordo: prima traccia
    handlers.get("nexttrack")?.();
    expect(onNext).toHaveBeenCalledOnce();
  });

  it("l'handler play comanda l'elemento audio", () => {
    const { handlers } = installMediaSession();
    render(<PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />);
    handlers.get("play")?.();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("allo smontaggio azzera metadata e handler", () => {
    const { ms, handlers } = installMediaSession();
    const { unmount } = render(
      <PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />,
    );
    unmount();
    expect(ms.metadata).toBeNull();
    expect(handlers.get("play")).toBeNull();
    expect(handlers.get("pause")).toBeNull();
  });

  it("senza navigator.mediaSession non esplode", () => {
    expect(() =>
      render(<PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />),
    ).not.toThrow();
  });
});
