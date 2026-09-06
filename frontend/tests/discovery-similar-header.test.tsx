import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DiscoverySimilarHeader } from "@/components/discovery-similar-header";
import type { DiscoverySimilarResponse } from "@/lib/api/types";

afterEach(cleanup);

const TRACK = { id: 1, artist: "Jasmín", title: "Bite The Hand",
                album_art_url: null } as never;

function data(over: Partial<DiscoverySimilarResponse> = {}): DiscoverySimilarResponse {
  return {
    track_id: 1,
    source: "bandcamp",
    origin: {
      artist: "Jasmín", title: "Bite The Hand That Feeds You",
      label: "Hessle Audio", year: 2025, tag: "bass",
      source_url: "https://x.bandcamp.com/album/y", resolution: "release",
    },
    edges: {
      same_artist: { count: 4, absent_reason: null },
      same_label: { count: 31, absent_reason: null },
      same_period_style: { count: null, absent_reason: "off" },
    },
    leads: [],
    ...over,
  };
}

describe("DiscoverySimilarHeader", () => {
  it("mostra la release riconosciuta con etichetta e anno", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} />);
    expect(screen.getByText(/Bite The Hand That Feeds You/)).toBeTruthy();
    expect(screen.getByText(/Hessle Audio/)).toBeTruthy();
    expect(screen.getByText(/2025/)).toBeTruthy();
  });

  it("dice quando la release non è stata riconosciuta", () => {
    render(<DiscoverySimilarHeader
      data={data({ origin: { ...data().origin!, resolution: "artist_only", title: null } })}
      track={TRACK} />);
    expect(screen.getByText(/Release non riconosciuta/)).toBeTruthy();
  });

  it("mostra il conteggio degli archi percorsi", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} />);
    expect(screen.getByText(/Artista/).textContent).toContain("4");
    expect(screen.getByText(/Etichetta/).textContent).toContain("31");
  });

  it("un arco assente porta il motivo, non un conteggio a zero", () => {
    render(<DiscoverySimilarHeader
      data={data({ edges: { ...data().edges,
        same_label: { count: null, absent_reason: "self_released" } } })}
      track={TRACK} />);
    const chip = screen.getByText(/Etichetta/);
    expect(chip.textContent).not.toContain("0");
    expect(chip.getAttribute("title") ?? "").toContain("Autoprodotto");
  });

  it("mostra la copertina della traccia di partenza", () => {
    const track = { ...(TRACK as object), album_art_url: "https://x/art.jpg" } as never;
    const { container } = render(<DiscoverySimilarHeader data={data()} track={track} />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("https://x/art.jpg");
    // Decorativa: artista e titolo sono già scritti accanto.
    expect(img?.getAttribute("alt")).toBe("");
  });

  it("senza copertina in rete la cerca nel file posseduto", () => {
    // La traccia di partenza è sempre posseduta: se `album_art_url` manca, la
    // copertina sta dentro al file e la serve l'endpoint disco.
    const track = { ...(TRACK as object), has_local_file: true } as never;
    const { container } = render(<DiscoverySimilarHeader data={data()} track={track} />);
    expect(container.querySelector("img")?.getAttribute("src")).toContain(
      "/api/tracks/1/cover");
  });

  it("senza copertina da nessuna parte mette il segnaposto, non un'immagine vuota", () => {
    const { container } = render(<DiscoverySimilarHeader data={data()} track={TRACK} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg.lucide-music-4")).not.toBeNull();
  });

  it("la release riconosciuta porta il title che dice cos'è", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} />);
    const block = screen.getByText(/Bite The Hand That Feeds You/).closest("div");
    expect(block?.getAttribute("title")).toBe("Release riconosciuta su Bandcamp");
  });
});
