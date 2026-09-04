import { describe, expect, it } from "vitest";

import { planAccept, groupOrder, issueIsFixable, issueIsStrong } from "@/lib/organize/issue-actions";
import type { Issue } from "@/lib/organize/api";

// Fabbrica minimale: i campi che il piano non guarda restano fissi.
function issue(over: Partial<Issue> & { id: number }): Issue {
  return {
    file_id: 1, location: "library", type: "missing_metadata", field: "genre",
    severity: "warning", detail: "", suggested_fix_json: null, status: "open",
    file_path: "/m/a.mp3", artist: "A", title: "T", current_value: null, is_new: false,
    ...over,
  };
}

describe("planAccept: cosa si accetta in blocco e come", () => {
  it("copertina, svuotamento e quarantena passano per il cambio di stato", () => {
    const list = [
      issue({ id: 1, type: "missing_cover", field: "cover", suggested_fix_json: { field: "cover", thumb_ref: "x" } }),
      issue({ id: 2, field: "comment", suggested_fix_json: { field: "comment", action: "clear" } }),
      issue({ id: 3, type: "corrupt_file", field: null, suggested_fix_json: { action: "quarantine" } }),
    ];
    const p = planAccept(list, {});
    expect(p.statusIds).toEqual([1, 2, 3]);
    expect(p.fixes).toEqual([]);
    expect(p.skipped).toBe(0);
  });

  it("un valore digitato a mano diventa una fix, anche senza suggerimento", () => {
    const list = [issue({ id: 5, field: "genre" })];
    const p = planAccept(list, { 5: "  Techno " });
    expect(p.statusIds).toEqual([]);
    expect(p.fixes).toEqual([{ id: 5, value: "Techno" }]);
    expect(p.skipped).toBe(0);
  });

  it("un suggerimento lasciato com'è si accetta per stato, non riscrivendolo", () => {
    // Così il suggested_fix_json originale (con `from`, source, confidence)
    // resta intatto: la fix serve solo quando l'utente ha cambiato il valore.
    const sug = { field: "artist", action: "retag", from: "a", to: "A", source: "provider", confidence: "high" };
    const list = [issue({ id: 6, field: "artist", suggested_fix_json: sug })];
    expect(planAccept(list, {}).statusIds).toEqual([6]);
    expect(planAccept(list, { 6: "A" }).statusIds).toEqual([6]);
    const changed = planAccept(list, { 6: "B" });
    expect(changed.statusIds).toEqual([]);
    expect(changed.fixes).toEqual([{ id: 6, value: "B" }]);
  });

  it("salta ciò che non ha nulla da applicare e lo conta", () => {
    const list = [
      issue({ id: 7, field: "genre" }),                          // editabile ma vuoto
      issue({ id: 8, field: "bpm" }),                            // campo non editabile
      issue({ id: 9, field: "genre", status: "accepted" }),      // già chiusa
      issue({ id: 10, field: "genre", suggested_fix_json: { field: "genre", action: "retag", to: "House" } }),
    ];
    const p = planAccept(list, { 7: "   " });
    expect(p.statusIds).toEqual([10]);
    expect(p.fixes).toEqual([]);
    expect(p.skipped).toBe(2); // la 9 non è aperta: non conta né come fatta né come saltata
    expect(p.total).toBe(1);
  });
});

describe("groupOrder: l'ordine dei gruppi non cambia accettando una riga", () => {
  const all = [
    issue({ id: 1, type: "missing_metadata" }),
    issue({ id: 2, type: "missing_metadata" }),
    issue({ id: 3, type: "missing_metadata", status: "accepted" }),
    issue({ id: 4, type: "dirty_genre" }),
    issue({ id: 5, type: "dirty_genre" }),
    issue({ id: 6, type: "dirty_genre", status: "accepted" }),
    issue({ id: 7, type: "inconsistent_casing" }),
  ];

  it("pesa sul totale (tutte le issue), non sulle sole aperte filtrate", () => {
    const rank = groupOrder(all, "type");
    // pari merito sul totale (3 e 3): spareggio alfabetico, stabile
    expect(rank("dirty_genre")).toBeLessThan(rank("missing_metadata"));
    expect(rank("missing_metadata")).toBeLessThan(rank("inconsistent_casing"));
  });

  it("la gravità ha un ordine fisso", () => {
    const rank = groupOrder(all, "severity");
    expect(rank("error")).toBeLessThan(rank("warning"));
    expect(rank("warning")).toBeLessThan(rank("info"));
  });
});

describe("predicati di riga", () => {
  it("fixable = azione applicabile o campo retaggabile", () => {
    expect(issueIsFixable(issue({ id: 1, field: "genre" }))).toBe(true);
    expect(issueIsFixable(issue({ id: 2, field: "bpm" }))).toBe(false);
    expect(issueIsFixable(issue({ id: 3, field: null, suggested_fix_json: { action: "quarantine" } }))).toBe(true);
  });

  it("strong solo da provider, mai dall'AI", () => {
    expect(issueIsStrong(issue({ id: 1, suggested_fix_json: { source: "provider", confidence: "high" } }))).toBe(true);
    expect(issueIsStrong(issue({ id: 2, suggested_fix_json: { source: "ai", confidence: "high" } }))).toBe(false);
  });
});
