import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DiscoveryLeadGrid } from "@/components/discovery-lead-grid";
import { PlayerProvider } from "@/lib/player";
import { it as itDict } from "@/lib/i18n/it";
import type { DiscoveryLead } from "@/lib/api/types";

afterEach(cleanup);

function lead(over: Partial<DiscoveryLead> = {}): DiscoveryLead {
  return {
    artist: "Pearson Sound", title: "Which Way Is Up", year: 2024,
    label: "Hessle Audio", style: null, source: "bandcamp", seed: "same_label",
    source_id: "1:2", source_url: null, stream_url: null, thumb_url: null,
    have: 0, want: 0, reasons: [{ code: "same_label", data: { label: "Hessle Audio" } }],
    format_badge: "EP",
    ...over,
  };
}

// La griglia non ha piu' un dig dentro: rende la lista che riceve e delega al
// chiamante lo stato vuoto (scavo e simili hanno cause diverse da spiegare).
function renderGrid(props: React.ComponentProps<typeof DiscoveryLeadGrid>) {
  // LeadCell usa usePlayer(), che fuori dal provider lancia.
  return render(<PlayerProvider><DiscoveryLeadGrid {...props} /></PlayerProvider>);
}

describe("DiscoveryLeadGrid", () => {
  it("rende i lead che riceve", () => {
    renderGrid({ leads: [lead()], empty: <p>niente</p> });
    expect(screen.getByText("Which Way Is Up")).toBeTruthy();
    expect(screen.getByText("Pearson Sound")).toBeTruthy();
    // Lo stato vuoto del chiamante non deve comparire quando ci sono lead.
    expect(screen.queryByText("niente")).toBeNull();
  });

  it("mostra lo stato vuoto che il chiamante le passa, senza inventarne uno", () => {
    renderGrid({ leads: [], empty: <p>stato vuoto del chiamante</p> });
    expect(screen.getByText("stato vuoto del chiamante")).toBeTruthy();
    // I vecchi stati vuoti del dig sono usciti da qui: se ricomparissero, la
    // griglia starebbe di nuovo raccontando una causa che non conosce.
    expect(screen.queryByText(itDict.discovery.nothingToDigTitle)).toBeNull();
    expect(screen.queryByText(itDict.discovery.noFormatMatch)).toBeNull();
  });

  it("il reason della stessa etichetta nomina l'etichetta", () => {
    renderGrid({ leads: [lead()], empty: null });
    expect(screen.getByText(itDict.discovery.reasonSameLabel("Hessle Audio"))).toBeTruthy();
  });

  it("il reason dello stesso artista ha un testo suo, non il codice grezzo", () => {
    renderGrid({
      leads: [lead({ reasons: [{ code: "same_artist", data: {} }] })],
      empty: null,
    });
    expect(screen.getByText(itDict.discovery.reasonSameArtist)).toBeTruthy();
    expect(screen.queryByText("same_artist")).toBeNull();
  });

  it("il reason di stile e periodo nomina il tag e gli anni", () => {
    renderGrid({
      leads: [lead({
        reasons: [{ code: "same_period_style", data: { tag: "uk bass", year_from: 2020, year_to: 2026 } }],
      })],
      empty: null,
    });
    expect(
      screen.getByText(itDict.discovery.reasonSamePeriodStyle("uk bass", 2020, 2026)),
    ).toBeTruthy();
  });
});
