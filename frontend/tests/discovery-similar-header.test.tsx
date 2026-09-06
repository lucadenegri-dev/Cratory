import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

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
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={() => {}} busy={false} />);
    expect(screen.getByText(/Bite The Hand That Feeds You/)).toBeTruthy();
    expect(screen.getByText(/Hessle Audio/)).toBeTruthy();
    expect(screen.getByText(/2025/)).toBeTruthy();
  });

  it("dice quando la release non è stata riconosciuta", () => {
    render(<DiscoverySimilarHeader
      data={data({ origin: { ...data().origin!, resolution: "artist_only", title: null } })}
      track={TRACK} stylePeriod={false} onStylePeriodChange={() => {}} busy={false} />);
    expect(screen.getByText(/Release non riconosciuta/)).toBeTruthy();
  });

  it("mostra il conteggio degli archi percorsi", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={() => {}} busy={false} />);
    expect(screen.getByText(/Artista/).textContent).toContain("4");
    expect(screen.getByText(/Etichetta/).textContent).toContain("31");
  });

  it("un arco assente porta il motivo, non un conteggio a zero", () => {
    render(<DiscoverySimilarHeader
      data={data({ edges: { ...data().edges,
        same_label: { count: null, absent_reason: "self_released" } } })}
      track={TRACK} stylePeriod={false} onStylePeriodChange={() => {}} busy={false} />);
    const chip = screen.getByText(/Etichetta/);
    expect(chip.textContent).not.toContain("0");
    expect(chip.getAttribute("title") ?? "").toContain("Autoprodotto");
  });

  it("l'interruttore stile e periodo avvisa il chiamante", () => {
    const onChange = vi.fn();
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={onChange} busy={false} />);
    fireEvent.click(screen.getByLabelText(/Stile e periodo/));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("la release riconosciuta porta il title che dice cos'è", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={() => {}} busy={false} />);
    const block = screen.getByText(/Bite The Hand That Feeds You/).closest("div");
    expect(block?.getAttribute("title")).toBe("Release riconosciuta su Bandcamp");
  });
});
