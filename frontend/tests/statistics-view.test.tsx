import { cleanup, render, screen, within } from "@testing-library/react";
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

  // La copertura non e' piu' tre barre di percentuale (erano tutte e tre
  // praticamente uguali): e' il rapporto assoluto piu' il buco su cui agire.
  it("la copertura mostra il rapporto pronte/totali e il residuo cliccabile", () => {
    render(<StatisticsView stats={stats()} labels={[]} />);
    const band = screen.getByText("Copertura").closest("section") as HTMLElement;
    expect(within(band).getByText("150")).toBeTruthy();    // ready_for_set
    expect(within(band).getByText("/ 200")).toBeTruthy();  // total_tracks
    const gap = within(band).getByText("50 senza BPM o tonalità →");  // 200 - 150
    expect(gap.closest("a")?.getAttribute("href")).toBe("/library?incomplete=1");
  });

  it("la barra di copertura riporta la percentuale come progressbar", () => {
    render(<StatisticsView stats={stats()} labels={[]} />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("75");
  });

  it("l'energia mostra i conteggi dei bucket e gli estremi dell'asse", () => {
    render(<StatisticsView stats={stats()} labels={[]} />);
    expect(screen.getByText("60")).toBeTruthy();
    expect(screen.getByText("140")).toBeTruthy();
  });

  // Le 24 tonalita' vivono in una matrice 12 x A/B: ogni cella e' un link al
  // filtro di libreria per quella tonalita', anche quando vale zero.
  it("la matrice Camelot rende tutte le 24 posizioni e linka alla libreria", () => {
    render(<StatisticsView stats={stats()} labels={[]} />);
    expect(screen.getByLabelText("8A · 30 tracce").getAttribute("href")).toBe("/library?key=8A");
    expect(screen.getByLabelText("11B · 10 tracce").getAttribute("href")).toBe("/library?key=11B");
    expect(screen.getByLabelText("6B · 0 tracce")).toBeTruthy();
  });

  // Le label sono spezzate in due colonne: senza una scala condivisa la prima
  // della seconda colonna disegnerebbe una barra lunga quanto la piu' alta.
  it("le barre delle label condividono la scala fra le due colonne", () => {
    const rows = Array.from({ length: 10 }, (_, i) => label(`L${i}`, 100 - i * 10));
    const { container } = render(<StatisticsView stats={stats()} labels={rows} />);
    const first = container.querySelector('a[href="/labels/L0"] span span') as HTMLElement;
    const sixth = container.querySelector('a[href="/labels/L5"] span span') as HTMLElement;
    expect(first.style.width).toBe("100%");
    expect(sixth.style.width).toBe("50%");   // 50/100, non 50/50
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
