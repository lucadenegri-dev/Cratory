import { describe, expect, it } from "vitest";

import { CAMELOT_KEYS, camelotRank, normalizeCamelot } from "@/lib/camelot";
import { defaultDir, filterMaterial, sortMaterial } from "@/lib/material-view";
import type { MaterialItem } from "@/lib/api";

const item = (id: number, bpm: number | null, key: string | null, added: string | null = null): MaterialItem => ({
  track: {
    id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
    title: `T${id}`, artist: "A", album: null, genre: null, year: null, duration_seconds: 300,
    bpm, camelot_key: key, energy: null, label: null, status: "imported", url: null, isrc: null,
    playlists: [], added_at: null, spotify_url: null, album_art_url: null, has_local_file: true, rating: null,
  } as unknown as MaterialItem["track"],
  in_set: false, from_playlist: added !== null, in_reserve: false, playlist_added_at: added,
});

const ids = (items: MaterialItem[]) => items.map((it) => it.track.id);

describe("camelot", () => {
  it("la ruota va 1A, 1B, 2A … 12B, non in ordine alfabetico", () => {
    expect(CAMELOT_KEYS.slice(0, 4)).toEqual(["1A", "1B", "2A", "2B"]);
    expect(CAMELOT_KEYS).toHaveLength(24);
    expect(CAMELOT_KEYS.at(-1)).toBe("12B");
    expect(camelotRank("2A")).toBeLessThan(camelotRank("10A"));
    expect(camelotRank("8A")).toBeLessThan(camelotRank("8B"));
  });

  it("normalizza maiuscole e spazi, e rifiuta cio' che non e' Camelot", () => {
    expect(normalizeCamelot(" 8a ")).toBe("8A");
    expect(normalizeCamelot("13A")).toBeNull();
    expect(normalizeCamelot("Am")).toBeNull();
    expect(normalizeCamelot(null)).toBeNull();
  });
});

describe("sortMaterial", () => {
  // 2 e 4 hanno la stessa tonalita' e 4 e 5 lo stesso BPM, messi apposta
  // contro l'ordine del server: senza il criterio di parita' il test se ne accorge.
  const items = [item(1, 126, "10A", "2026-02-01T00:00:00"), item(2, 124, "2A", null),
    item(3, null, null, "2026-03-01T00:00:00"), item(4, 122, "2A", "2026-01-01T00:00:00"),
    item(5, 122, "1B", null)];

  it("«playlist» lascia l'ordine del server", () => {
    expect(ids(sortMaterial(items, "playlist", "asc"))).toEqual([1, 2, 3, 4, 5]);
  });

  it("tonalita' sulla ruota, a parita' di tonalita' per BPM, senza tonalita' in fondo", () => {
    expect(ids(sortMaterial(items, "key", "asc"))).toEqual([5, 4, 2, 1, 3]);
  });

  it("tonalita' al contrario: la ruota si inverte ma chi non ha tonalita' resta in fondo", () => {
    expect(ids(sortMaterial(items, "key", "desc"))).toEqual([1, 4, 2, 5, 3]);
  });

  it("BPM, a parita' di BPM per tonalita', senza BPM in fondo in entrambi i versi", () => {
    expect(ids(sortMaterial(items, "bpm", "asc"))).toEqual([5, 4, 2, 1, 3]);
    expect(ids(sortMaterial(items, "bpm", "desc"))).toEqual([1, 2, 5, 4, 3]);
  });

  it("aggiunta: le piu' recenti prima, senza data in fondo nell'ordine del server", () => {
    expect(ids(sortMaterial(items, "added", "desc"))).toEqual([3, 1, 4, 2, 5]);
    expect(ids(sortMaterial(items, "added", "asc"))).toEqual([4, 1, 3, 2, 5]);
  });

  it("non tocca l'array di partenza", () => {
    sortMaterial(items, "bpm", "asc");
    expect(ids(items)).toEqual([1, 2, 3, 4, 5]);
  });

  it("il verso predefinito: aggiunta dalle piu' recenti, il resto crescente", () => {
    expect(defaultDir("added")).toBe("desc");
    expect(defaultDir("key")).toBe("asc");
    expect(defaultDir("bpm")).toBe("asc");
  });
});

describe("filterMaterial", () => {
  const items = [item(1, 120, "8A"), item(2, 124.5, "8a"), item(3, null, "8A"),
    item(4, 128, null), item(5, 130, "11A")];

  it("senza filtri passa tutto", () => {
    expect(ids(filterMaterial(items, { bpmMin: null, bpmMax: null, key: null }))).toEqual([1, 2, 3, 4, 5]);
  });

  it("BPM min e max sono inclusivi e chi non ha BPM esce", () => {
    expect(ids(filterMaterial(items, { bpmMin: 124, bpmMax: 128, key: null }))).toEqual([2, 4]);
    expect(ids(filterMaterial(items, { bpmMin: 125, bpmMax: null, key: null }))).toEqual([4, 5]);
    expect(ids(filterMaterial(items, { bpmMin: null, bpmMax: 120, key: null }))).toEqual([1]);
  });

  it("tonalita' esatta: 1A non prende 11A, le minuscole contano come maiuscole", () => {
    expect(ids(filterMaterial(items, { bpmMin: null, bpmMax: null, key: "8A" }))).toEqual([1, 2, 3]);
    expect(ids(filterMaterial([...items, item(6, 120, "1A")], { bpmMin: null, bpmMax: null, key: "1A" }))).toEqual([6]);
  });
});
