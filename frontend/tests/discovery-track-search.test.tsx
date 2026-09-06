import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { DiscoveryTrackSearch } from "@/components/discovery-track-search";

afterEach(() => { cleanup(); vi.useRealTimers(); });

const A = { id: 5, artist: "Jasmín", title: "Bite The Hand", album_art_url: null, has_local_file: true } as never;
const B = { id: 9, artist: "Pearson Sound", title: "Jasmine Tea", album_art_url: null, has_local_file: true } as never;

function setup(results = [A, B]) {
  const search = vi.fn().mockResolvedValue(results);
  const onPick = vi.fn();
  render(<DiscoveryTrackSearch search={search} onPick={onPick} />);
  return { search, onPick };
}

const input = () => screen.getByRole("combobox") as HTMLInputElement;

describe("DiscoveryTrackSearch", () => {
  it("cerca dopo una pausa, non a ogni tasto", async () => {
    vi.useFakeTimers();
    const { search } = setup();
    fireEvent.change(input(), { target: { value: "j" } });
    fireEvent.change(input(), { target: { value: "ja" } });
    fireEvent.change(input(), { target: { value: "jas" } });
    expect(search).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(300); });
    expect(search).toHaveBeenCalledTimes(1);
    expect(search).toHaveBeenCalledWith("jas");
  });

  it("mostra artista — titolo e sceglie al click", async () => {
    const { onPick } = setup();
    fireEvent.change(input(), { target: { value: "jas" } });
    await waitFor(() => expect(screen.getByText(/Bite The Hand/)).toBeTruthy());
    fireEvent.mouseDown(screen.getByText(/Jasmine Tea/));
    expect(onPick).toHaveBeenCalledWith(B);
  });

  it("frecce e Invio scelgono da tastiera", async () => {
    const { onPick } = setup();
    fireEvent.change(input(), { target: { value: "jas" } });
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(B);
  });

  it("nessun risultato lo dice", async () => {
    setup([]);
    fireEvent.change(input(), { target: { value: "zzz" } });
    await waitFor(() => expect(screen.getByText("Nessuna traccia trovata")).toBeTruthy());
  });

  it("una risposta arrivata in ritardo per una query vecchia non sovrascrive", async () => {
    let releaseOld: (v: unknown[]) => void = () => {};
    const search = vi.fn()
      .mockImplementationOnce(() => new Promise((res) => { releaseOld = res; }))
      .mockResolvedValueOnce([B]);
    render(<DiscoveryTrackSearch search={search} onPick={() => {}} />);
    fireEvent.change(input(), { target: { value: "ja" } });
    await waitFor(() => expect(search).toHaveBeenCalledTimes(1));
    fireEvent.change(input(), { target: { value: "jasmine" } });
    await waitFor(() => expect(screen.getByText(/Jasmine Tea/)).toBeTruthy());
    await act(async () => { releaseOld([A]); });
    expect(screen.queryByText(/Bite The Hand/)).toBeNull();
  });

  it("campo vuoto: niente ricerca, niente lista", async () => {
    const { search } = setup();
    fireEvent.change(input(), { target: { value: "  " } });
    await new Promise((r) => setTimeout(r, 320));
    expect(search).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
