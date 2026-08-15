import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Colophon } from "@/components/dashboard/colophon";
import type { LabelStats, LibraryStats } from "@/lib/api";

function stats(over: Partial<LibraryStats> = {}): LibraryStats {
  return {
    total_tracks: 100, playlists: 4, by_source: {}, with_bpm: 90, with_key: 90,
    with_features: 0, with_local_file: 60, ready_for_set: 80, missing_metadata: 5,
    bpm_min: 120, bpm_max: 138,
    key_distribution: { "8A": 20, "5A": 15, "11B": 10, "3A": 8, "9B": 6, "1A": 2 },
    genre_distribution: { Techno: 40, House: 25, Electro: 10, Ambient: 5, Dub: 2 },
    bpm_histogram: [{ from: 120, to: 129, count: 40 }, { from: 129, to: 138, count: 50 }],
    energy_distribution: [],
    ...over,
  };
}

function label(name: string, count: number): LabelStats {
  return {
    label: name, track_count: count, artist_count: 1, artists: [], genres: [],
    year_min: null, year_max: null,
  };
}

const LABELS: LabelStats[] = [
  label("Ostgut Ton", 12),
  label("Hessle Audio", 9),
  label("Livity Sound", 7),
  label("Quarta", 1),
];

describe("colophon", () => {
  afterEach(cleanup);

  it("rende il range BPM con la sparkline", () => {
    const { container } = render(<Colophon stats={stats()} labels={LABELS} />);
    expect(container.textContent).toContain("120–138");
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
  });

  it("mostra le prime 5 tonalità, i primi 4 generi e le prime 3 label", () => {
    render(<Colophon stats={stats()} labels={LABELS} />);
    expect(screen.getByText("8A")).toBeTruthy();
    expect(screen.queryByText("1A")).toBeNull();       // sesta tonalità: fuori
    expect(screen.getByText("Techno")).toBeTruthy();
    expect(screen.queryByText("Dub")).toBeNull();       // quinto genere: fuori
    expect(screen.getByText("Ostgut Ton")).toBeTruthy();
    expect(screen.queryByText("Quarta")).toBeNull();    // quarta label: fuori
  });

  it("generi e label sono link alle rispettive pagine", () => {
    render(<Colophon stats={stats()} labels={LABELS} />);
    expect(screen.getByText("Techno").closest("a")?.getAttribute("href")).toBe("/library?genre=Techno");
    expect(screen.getByText("Ostgut Ton").closest("a")?.getAttribute("href")).toBe("/labels/Ostgut%20Ton");
  });

  it("omette la singola riga senza dati, tenendo le altre", () => {
    const senzaGeneri = stats({ genre_distribution: {} });
    render(<Colophon stats={senzaGeneri} labels={LABELS} />);
    expect(screen.queryByText("Generi")).toBeNull();
    // Le righe con dati restano: l'omissione è per riga, non tutto-o-niente.
    expect(screen.getByText("BPM")).toBeTruthy();
    expect(screen.getByText("Tonalità")).toBeTruthy();
    expect(screen.getByText("Label")).toBeTruthy();
  });

  it("omette le righe senza dati, niente segnaposto", () => {
    const vuote = stats({ bpm_min: null, bpm_max: null, bpm_histogram: [], key_distribution: {}, genre_distribution: {} });
    render(<Colophon stats={vuote} labels={[]} />);
    expect(screen.queryByText("BPM")).toBeNull();
    expect(screen.queryByText("Tonalità")).toBeNull();
    expect(screen.queryByText("Generi")).toBeNull();
    expect(screen.queryByText("Label")).toBeNull();
  });
});
