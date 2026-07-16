import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DockedPlayer } from "@/components/docked-player";
import { TrackPlayButton } from "@/components/track-play-button";
import { PlayerProvider } from "@/lib/player";

function renderButton(track: { id: number; title: string; artist: string; has_local_file: boolean }) {
  return render(
    <PlayerProvider>
      <TrackPlayButton track={track} />
      <DockedPlayer />
    </PlayerProvider>,
  );
}

describe("track play button", () => {
  afterEach(cleanup);

  it("non si renderizza senza file locale", () => {
    renderButton({ id: 5, title: "T", artist: "A", has_local_file: false });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("riproduce la traccia: l'audio docked punta all'endpoint di streaming", async () => {
    renderButton({ id: 5, title: "T", artist: "A", has_local_file: true });
    await act(async () => {
      screen.getByRole("button").click();
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
  });

  it("mostra il messaggio di formato non supportato quando l'audio va in errore", async () => {
    renderButton({ id: 7, title: "T", artist: "A", has_local_file: true });
    await act(async () => {
      screen.getByRole("button").click();
    });
    const audio = screen.getByTestId("local-audio");
    await act(async () => {
      fireEvent.error(audio);
    });
    expect(screen.queryByTestId("local-audio")).toBeNull();
    expect(screen.getByText(/browser/i)).toBeTruthy();
  });
});
