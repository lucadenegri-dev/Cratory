import { describe, expect, it } from "vitest";

import { findTopPlaylist, pickRandom } from "@/lib/random-track";
import type { Playlist } from "@/lib/api";

function pl(id: number, name: string): Playlist {
  return {
    id, platform: "spotify", platform_playlist_id: null, name, owner: null, url: null,
    artwork_url: null, track_count: 10, kind: "imported", name_locked: false,
    imported_at: "2026-08-01T00:00:00Z",
  };
}

describe("findTopPlaylist", () => {
  it("trova la playlist Top comunque sia scritta", () => {
    for (const name of ["Top", "top", "TOP", "  Top  "]) {
      expect(findTopPlaylist([pl(1, "Acid"), pl(2, name)])?.id).toBe(2);
    }
  });

  it("non confonde un nome che contiene 'top' con la playlist Top", () => {
    expect(findTopPlaylist([pl(1, "Topolino"), pl(2, "Rooftop")])).toBeNull();
  });

  it("senza playlist Top restituisce null: chi chiama ripiega", () => {
    expect(findTopPlaylist([pl(1, "Acid")])).toBeNull();
    expect(findTopPlaylist([])).toBeNull();
  });
});

describe("pickRandom", () => {
  it("pesca l'elemento all'indice indicato dal generatore", () => {
    const items = ["a", "b", "c"];
    expect(pickRandom(items, () => 0)).toBe("a");
    expect(pickRandom(items, () => 0.5)).toBe("b");
    expect(pickRandom(items, () => 0.999)).toBe("c");
  });

  it("su lista vuota restituisce null invece di undefined", () => {
    expect(pickRandom([], () => 0)).toBeNull();
  });

  it("copre tutta la lista, non solo il primo elemento", () => {
    const items = [1, 2, 3, 4, 5];
    const seen = new Set(items.map((_, i) => pickRandom(items, () => i / items.length)));
    expect(seen.size).toBe(5);
  });
});
