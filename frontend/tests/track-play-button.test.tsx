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

  const CTX = [
    { id: 5, title: "T", artist: "A", has_local_file: true },
    { id: 6, title: "U", artist: "A", has_local_file: true },
    { id: 7, title: "V", artist: "A", has_local_file: false }, // non posseduta: esclusa dal contesto
  ];

  function renderWithContext() {
    return render(
      <PlayerProvider>
        <TrackPlayButton track={CTX[0]} context={CTX} />
        <DockedPlayer />
      </PlayerProvider>,
    );
  }

  it("con contesto: a fine traccia avanza alla successiva posseduta", async () => {
    renderWithContext();
    await act(async () => {
      screen.getByRole("button").click();
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/6/audio");
  });

  it("il contesto salta le tracce non possedute: dopo la 6 non c'è una next", async () => {
    renderWithContext();
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    // id 7 non ha file: il contesto filtrato finisce con la 6
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/6/audio");
  });

  it("senza contesto: a fine traccia non avanza", async () => {
    renderButton({ id: 5, title: "T", artist: "A", has_local_file: true });
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
  });
});
