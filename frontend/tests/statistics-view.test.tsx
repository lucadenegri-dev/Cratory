import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatisticsView } from "@/components/statistics/statistics-view";
import type { LabelStats, LibraryStats } from "@/lib/api";

function stats(over: Partial<LibraryStats> = {}): LibraryStats {
  return {
    total_tracks: 200, playlists: 4,
    by_source: { spotify: 120, soundcloud: 40, manual: 10, local_files: 30 },
    with_bpm: 180, with_key: 160, with_features: 150, with_local_file: 90,
    ready_for_set: 150, missing_metadata: 5,
    bpm_min: 118, bpm_max: 150,
    key_distribution: { "8A": 30, "5A": 20, "11B": 10 },
    genre_distribution: { Techno: 80, House: 40 },
    bpm_histogram: [{ from: 118, to: 134, count: 90 }, { from: 134, to: 150, count: 110 }],
    energy_distribution: [
      { from: 0, to: 0.5, count: 60 },
      { from: 0.5, to: 1, count: 140 },
    ],
    ...over,
  };
}

function label(name: string, count: number): LabelStats {
  return {
    label: name, track_count: count, artist_count: 1, artists: [], genres: [],
    year_min: null, year_max: null,
  };
}

describe("statistics view", () => {
  afterEach(cleanup);

  it("con dati pieni mostra tutte e sette le sezioni", () => {
    render(<StatisticsView stats={stats()} labels={[label("Ostgut Ton", 12)]} />);
    for (const heading of ["Istogramma BPM", "Tonalità", "Generi", "Label", "Energia", "Fonti", "Copertura"]) {
      expect(screen.getByText(heading)).toBeTruthy();
    }
  });

  it("generi e label linkano alle rispettive pagine", () => {
    render(<StatisticsView stats={stats()} labels={[label("Ostgut Ton", 12)]} />);
    expect(screen.getByText("Techno").closest("a")?.getAttribute("href")).toBe("/library?genre=Techno");
    expect(screen.getByText("Ostgut Ton").closest("a")?.getAttribute("href")).toBe("/labels/Ostgut%20Ton");
  });

  it("la copertura mostra le percentuali giuste sul totale", () => {
    render(<StatisticsView stats={stats()} labels={[]} />);
    expect(screen.getByText("90%")).toBeTruthy();  // 180/200 con BPM
    expect(screen.getByText("80%")).toBeTruthy();  // 160/200 con tonalità
    expect(screen.getByText("75%")).toBeTruthy();  // 150/200 pronte
  });

  it("l'energia etichetta i bucket come intervallo from–to", () => {
    render(<StatisticsView stats={stats()} labels={[]} />);
    expect(screen.getByText("0.5–1")).toBeTruthy();
  });

  it("una sezione senza dati si omette, le altre restano", () => {
    render(
      <StatisticsView
        stats={stats({ genre_distribution: {}, energy_distribution: [] })}
        labels={[]}
      />,
    );
    expect(screen.queryByText("Generi")).toBeNull();
    expect(screen.queryByText("Energia")).toBeNull();
    expect(screen.queryByText("Label")).toBeNull();
    expect(screen.getByText("Tonalità")).toBeTruthy();
    expect(screen.getByText("Copertura")).toBeTruthy();
  });
});
