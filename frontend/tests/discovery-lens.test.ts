import { describe, expect, it } from "vitest";

import { applyLens } from "@/components/discovery-lead-grid";
import type { DiscoveryLead } from "@/lib/api/types";

function lead(over: Partial<DiscoveryLead>): DiscoveryLead {
  return {
    artist: "A", title: "T", year: 2000, label: null, style: null,
    source: "discogs", seed: null, source_id: null, source_url: null, stream_url: null,
    thumb_url: null, have: 0, want: 0, reasons: [], format_badge: null,
    ...over,
  };
}

describe("applyLens", () => {
  // 200 LP (anni 1990-2019 a rotazione) + 40 EP: abbastanza da far mordere ogni taglio.
  const LEADS = [
    ...Array.from({ length: 200 }, (_, i) =>
      lead({ title: `lp${i}`, format_badge: "LP", year: 1990 + (i % 30) })),
    ...Array.from({ length: 40 }, (_, i) => lead({ title: `ep${i}`, format_badge: "EP" })),
  ];

  it("taglia DOPO il filtro di formato: i numeri non mentono", () => {
    // Con formato EP selezionato il conteggio deve dire "40 di 40", non "40 di 240":
    // `total` conta cio' che il filtro ha lasciato, e visible/total escono dalla
    // stessa funzione — non possono divergere.
    const { visible, total } = applyLens(LEADS, { format: "EP", sort: "score", show: 80 });
    expect(total).toBe(40);
    expect(visible.length).toBe(40);
  });

  it("show=40 su 240 lead: 40 visibili, total 240", () => {
    const { visible, total } = applyLens(LEADS, { format: null, sort: "score", show: 40 });
    expect(visible.length).toBe(40);
    expect(total).toBe(240);
  });

  it("show='all' mostra tutto", () => {
    expect(applyLens(LEADS, { format: null, sort: "score", show: "all" }).visible.length).toBe(240);
  });

  it("sort='recent' ordina per anno decrescente prima del taglio", () => {
    const { visible } = applyLens(LEADS, { format: "LP", sort: "recent", show: 40 });
    expect(visible[0].year).toBe(2019);
  });

  it("sort='score' conserva l'ordine di arrivo (il gusto ha gia' ordinato)", () => {
    const { visible } = applyLens(LEADS, { format: null, sort: "score", show: 3 });
    expect(visible.map((l) => l.title)).toEqual(["lp0", "lp1", "lp2"]);
  });
});
