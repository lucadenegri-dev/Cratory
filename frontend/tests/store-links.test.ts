import { describe, expect, it } from "vitest";
import { STORES, storeQuery } from "@/lib/store-links";

describe("storeQuery", () => {
  it("unisce artista e titolo urlencoded", () => {
    expect(storeQuery("Marco Faraone", "Real Freak")).toBe("Marco%20Faraone%20Real%20Freak");
  });
  it("tollera artista o titolo mancanti", () => {
    expect(storeQuery(null, "Real Freak")).toBe("Real%20Freak");
    expect(storeQuery("Marco Faraone", null)).toBe("Marco%20Faraone");
  });
});

describe("STORES", () => {
  it("sono i 4 negozi della spec, nell'ordine", () => {
    expect(STORES.map((s) => s.key)).toEqual(["bandcamp", "beatport", "juno", "discogs"]);
  });
  it("generano gli URL di ricerca della spec", () => {
    const q = storeQuery("A", "B");
    const urls = Object.fromEntries(STORES.map((s) => [s.key, s.url(q)]));
    expect(urls.bandcamp).toBe("https://bandcamp.com/search?q=A%20B");
    expect(urls.beatport).toBe("https://www.beatport.com/search?q=A%20B");
    expect(urls.juno).toBe("https://www.junodownload.com/search/?q%5Ball%5D%5B%5D=A%20B");
    expect(urls.discogs).toBe("https://www.discogs.com/search/?q=A%20B&type=release");
  });
});
