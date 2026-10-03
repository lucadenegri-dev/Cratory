import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { MaterialPanel } from "@/components/set-builder/material-panel";
import type { Material } from "@/lib/api";
import { PlayerProvider } from "@/lib/player";

const track = (id: number, bpm: number | null, key: string | null) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}.`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm, camelot_key: key, energy: null, label: null, status: "imported",
  url: null, isrc: null, playlists: [], added_at: null, spotify_url: null, album_art_url: null,
  has_local_file: true, rating: null,
});

// Nell'ordine del server: 10A, 2A, senza tonalita', 1B.
const material = {
  sources: [{ playlist_id: 3, name: "Deep" }],
  items: [
    { track: track(1, 126, "10A"), playlist_added_at: "2026-02-01T00:00:00" },
    { track: track(2, 122, "2A"), playlist_added_at: "2026-03-05T00:00:00" },
    { track: track(3, null, null), playlist_added_at: null },
    { track: track(4, 124, "1B"), playlist_added_at: "2026-01-10T00:00:00" },
  ].map((it) => ({ ...it, in_set: false, from_playlist: true, in_reserve: false })),
} as unknown as Material;

const noop = vi.fn();
const mount = () => render(
  <PlayerProvider>
    <MaterialPanel material={material} query="" owned={false} unused={false} reserved={false}
      onQuery={noop} onOwned={noop} onUnused={noop} onReserved={noop} onAdd={noop}
      onReserve={noop} onAddAlternative={noop} canAddAlternative={false} />
  </PlayerProvider>,
);

const panel = () => within(screen.getByTestId("material-panel"));
const order = () => Array.from(screen.getByTestId("material-panel").querySelectorAll("li"),
  (li) => Number(/Traccia (\d+)\./.exec(li.textContent ?? "")?.[1]));

afterEach(cleanup);

describe("materiale: ordinamento", () => {
  it("parte dall'ordine della playlist", () => {
    mount();
    expect(order()).toEqual([1, 2, 3, 4]);
  });

  it("tonalita' sulla ruota; un secondo clic la gira, senza tonalita' resta in fondo", () => {
    mount();
    fireEvent.click(panel().getByRole("button", { name: "tonalità" }));
    expect(order()).toEqual([4, 2, 1, 3]);
    fireEvent.click(panel().getByRole("button", { name: "tonalità" }));
    expect(order()).toEqual([1, 2, 4, 3]);
  });

  it("BPM crescente", () => {
    mount();
    fireEvent.click(panel().getByRole("button", { name: "BPM" }));
    expect(order()).toEqual([2, 4, 1, 3]);
  });

  it("aggiunta: dalle piu' recenti, e la riga mostra la data", () => {
    mount();
    fireEvent.click(panel().getByRole("button", { name: "aggiunta" }));
    expect(order()).toEqual([2, 1, 4, 3]);
    expect(panel().getByText("05/03/26")).toBeTruthy();
  });

  it("tornare a «playlist» rimette l'ordine del server", () => {
    mount();
    fireEvent.click(panel().getByRole("button", { name: "BPM" }));
    fireEvent.click(panel().getByRole("button", { name: "playlist" }));
    expect(order()).toEqual([1, 2, 3, 4]);
  });
});

describe("materiale: filtri", () => {
  it("BPM min e max lasciano solo chi sta dentro, e il contatore lo dice", () => {
    mount();
    fireEvent.change(panel().getByPlaceholderText("BPM min"), { target: { value: "123" } });
    fireEvent.change(panel().getByPlaceholderText("BPM max"), { target: { value: "126" } });
    expect(order()).toEqual([1, 4]);
    expect(panel().getByText("2 di 4")).toBeTruthy();
  });

  it("la tonalita' e' esatta, e se non resta niente lo dice", () => {
    mount();
    const select = panel().getByRole("combobox", { name: "Tonalità" });
    fireEvent.change(select, { target: { value: "2A" } });
    expect(order()).toEqual([2]);
    fireEvent.change(select, { target: { value: "5B" } });
    expect(order()).toEqual([]);
    expect(panel().getByText("Nessuna traccia con questi filtri.")).toBeTruthy();
  });

  it("senza filtri attivi niente contatore", () => {
    mount();
    expect(panel().queryByText("4 di 4")).toBeNull();
  });
});
