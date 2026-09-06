import { describe, expect, it } from "vitest";

import {
  addSeed, digHref, encodeSeeds, MAX_SEEDS, parseSeeds, removeSeed, sameSeeds, seedKey,
  type DigSeed,
} from "@/lib/discovery-seeds";

const DEEP: DigSeed = { type: "genre", value: "Deep House" };
const HESSLE: DigSeed = { type: "label", value: "Hessle Audio" };

describe("i semi dello scavo", () => {
  it("la chiave ignora maiuscole e spazi ai bordi", () => {
    expect(seedKey({ type: "genre", value: "  deep HOUSE " })).toBe(seedKey(DEEP));
    expect(seedKey({ type: "label", value: "Deep House" })).not.toBe(seedKey(DEEP));
  });

  it("aggiungere un seme già presente non lo sdoppia e lo indica", () => {
    const r = addSeed([DEEP], { type: "genre", value: "deep house" });
    expect(r.seeds).toEqual([DEEP]);
    expect(r.duplicate).toEqual(DEEP);
    expect(r.full).toBe(false);
  });

  it("aggiunge in coda, col valore ripulito", () => {
    const r = addSeed([DEEP], { type: "label", value: " Hessle Audio " });
    expect(r.seeds).toEqual([DEEP, HESSLE]);
    expect(r.duplicate).toBeNull();
  });

  it("al quinto seme rifiuta e lo dice", () => {
    const four = Array.from({ length: MAX_SEEDS }, (_, i) => ({ type: "genre" as const, value: `G${i}` }));
    const r = addSeed(four, { type: "genre", value: "Uno di troppo" });
    expect(r.seeds).toEqual(four);
    expect(r.full).toBe(true);
  });

  it("un valore vuoto non entra", () => {
    expect(addSeed([], { type: "genre", value: "   " }).seeds).toEqual([]);
  });

  it("toglie per chiave, non per identità", () => {
    expect(removeSeed([DEEP, HESSLE], { type: "genre", value: "deep house" })).toEqual([HESSLE]);
  });

  it("URL: codifica i due punti e la virgola DENTRO il valore", () => {
    const seeds: DigSeed[] = [{ type: "genre", value: "Nu-Disco, Italo" }, { type: "label", value: "R:S" }];
    const raw = encodeSeeds(seeds);
    expect(raw).toBe("genre:Nu-Disco%2C%20Italo,label:R%3AS");
    expect(parseSeeds(raw)).toEqual(seeds);
  });

  it("URL: round-trip attraverso URLSearchParams", () => {
    const seeds: DigSeed[] = [DEEP, HESSLE];
    const href = digHref("/discovery", seeds, 0.5, "bandcamp");
    const params = new URLSearchParams(href.split("?")[1]);
    expect(parseSeeds(params.get("seeds"))).toEqual(seeds);
    expect(params.get("depth")).toBe("0.5");
    expect(params.get("source")).toBe("bandcamp");
  });

  it("il parser scarta tipi sconosciuti, valori vuoti e semi oltre il cap", () => {
    expect(parseSeeds("track:5,genre:House,label:")).toEqual([{ type: "genre", value: "House" }]);
    expect(parseSeeds(null)).toEqual([]);
    expect(parseSeeds("")).toEqual([]);
    const six = Array.from({ length: 6 }, (_, i) => `genre:G${i}`).join(",");
    expect(parseSeeds(six)).toHaveLength(MAX_SEEDS);
  });

  it("il parser non si rompe su una codifica malformata", () => {
    expect(parseSeeds("genre:%E0%A4%A")).toEqual([]);
  });

  it("sameSeeds confronta chiavi e ordine", () => {
    expect(sameSeeds([DEEP, HESSLE], [{ type: "genre", value: "deep house" }, HESSLE])).toBe(true);
    expect(sameSeeds([DEEP, HESSLE], [HESSLE, DEEP])).toBe(false);
    expect(sameSeeds([DEEP], [])).toBe(false);
  });
});
