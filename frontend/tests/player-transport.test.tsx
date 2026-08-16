import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerTransport } from "@/components/player-transport";

/* jsdom non implementa play()/pause(): i mock simulano l'elemento reale
   dispacciando gli eventi corrispondenti, così il componente reagisce come
   nel browser. */
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderTransport(extra: Partial<Parameters<typeof PlayerTransport>[0]> = {}) {
  const onAudible = vi.fn();
  const utils = render(
    <PlayerTransport src="/api/tracks/5/audio" testId="local-audio" onAudible={onAudible} {...extra} />,
  );
  return { onAudible, audio: screen.getByTestId("local-audio") as HTMLAudioElement, ...utils };
}

/** La durata in jsdom è NaN: la si finge come farebbe il browser a metadata caricati. */
function setDuration(audio: HTMLAudioElement, v: number) {
  Object.defineProperty(audio, "duration", { configurable: true, get: () => v });
  fireEvent.durationChange(audio);
}

describe("PlayerTransport", () => {
  it("senza durata: tempi a riposo e seek disabilitato", () => {
    renderTransport();
    expect(screen.getByText("0:00")).toBeTruthy();
    expect(screen.getByText("–:––")).toBeTruthy();
    expect((screen.getByLabelText("Posizione") as HTMLInputElement).disabled).toBe(true);
  });

  it("mostra durata e posizione formattate mm:ss", () => {
    const { audio } = renderTransport();
    setDuration(audio, 187);
    expect(screen.getByText("3:07")).toBeTruthy();
    Object.defineProperty(audio, "currentTime", { configurable: true, value: 65, writable: true });
    fireEvent.timeUpdate(audio);
    expect(screen.getByText("1:05")).toBeTruthy();
  });

  it("il riempimento della timeline segue la posizione", () => {
    const { audio } = renderTransport();
    const seek = screen.getByLabelText("Posizione") as HTMLInputElement;
    // Senza durata nota non c'e' progresso da mostrare.
    expect(seek.style.getPropertyValue("--p")).toBe("0%");
    setDuration(audio, 200);
    Object.defineProperty(audio, "currentTime", { configurable: true, value: 50, writable: true });
    fireEvent.timeUpdate(audio);
    expect(seek.style.getPropertyValue("--p")).toBe("25%");
  });

  it("il seek imposta currentTime sull'elemento", () => {
    const { audio } = renderTransport();
    setDuration(audio, 200);
    let ct = 0;
    Object.defineProperty(audio, "currentTime", { configurable: true, get: () => ct, set: (v) => { ct = v; } });
    fireEvent.change(screen.getByLabelText("Posizione"), { target: { value: "30" } });
    expect(ct).toBe(30);
  });

  it("play/pause: il bottone comanda l'elemento e riflette lo stato reale", async () => {
    const { audio, onAudible } = renderTransport();
    await act(async () => {
      fireEvent.play(audio); // autoplay partito
    });
    expect(onAudible).toHaveBeenLastCalledWith(true);
    const btn = screen.getByLabelText("Pausa");
    await act(async () => {
      btn.click();
    });
    expect(onAudible).toHaveBeenLastCalledWith(false);
    expect(screen.getByLabelText("Ascolta")).toBeTruthy(); // tornato "play"
    await act(async () => {
      screen.getByLabelText("Ascolta").click();
    });
    expect(onAudible).toHaveBeenLastCalledWith(true);
  });

  it("ended: pubblica il silenzio e chiama onEnded", async () => {
    const onEnded = vi.fn();
    const { audio, onAudible } = renderTransport({ onEnded });
    await act(async () => {
      fireEvent.play(audio);
      fireEvent.ended(audio);
    });
    expect(onAudible).toHaveBeenLastCalledWith(false);
    expect(onEnded).toHaveBeenCalledOnce();
  });

  it("error: chiama onError", () => {
    const onError = vi.fn();
    const { audio } = renderTransport({ onError });
    fireEvent.error(audio);
    expect(onError).toHaveBeenCalledOnce();
  });

  it("prev/next: assenti senza contesto, presenti e cablati con contesto", async () => {
    renderTransport();
    expect(screen.queryByLabelText("Traccia successiva")).toBeNull();
    cleanup();
    const onPrev = vi.fn();
    const onNext = vi.fn();
    renderTransport({ prevNext: { hasPrev: false, hasNext: true, onPrev, onNext } });
    const prevBtn = screen.getByLabelText("Traccia precedente") as HTMLButtonElement;
    expect(prevBtn.disabled).toBe(true);
    await act(async () => {
      screen.getByLabelText("Traccia successiva").click();
    });
    expect(onNext).toHaveBeenCalledOnce();
    expect(onPrev).not.toHaveBeenCalled();
  });
});
