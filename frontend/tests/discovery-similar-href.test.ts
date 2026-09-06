import { describe, expect, it } from "vitest";
import { similarHref } from "@/lib/discovery-dig";

describe("similarHref", () => {
  it("porta l'id della traccia e l'interruttore spento", () => {
    expect(similarHref(42, false)).toBe("/discovery?similar=42&style_period=0");
  });

  it("accende l'interruttore nell'URL", () => {
    expect(similarHref(42, true)).toBe("/discovery?similar=42&style_period=1");
  });

  it("porta con sé l'origine, così la traccia ritrovata sa da dove venivi", () => {
    expect(similarHref(42, false, "/library?genre=Techno&sort=bpm")).toBe(
      "/discovery?similar=42&style_period=0&from=%2Flibrary%3Fgenre%3DTechno%26sort%3Dbpm",
    );
  });

  it("senza origine non aggiunge il parametro, invece di scriverlo vuoto", () => {
    expect(similarHref(42, false, null)).toBe("/discovery?similar=42&style_period=0");
    expect(similarHref(42, false, "")).toBe("/discovery?similar=42&style_period=0");
  });

  it("codifica l'origine invece di spezzare la query string", () => {
    // Senza codifica, una & dentro `from` diventerebbe un parametro a sé e
    // `similar` verrebbe letto male dalla pagina.
    const href = similarHref(7, true, "/playlists/detail?id=3&q=a b");
    expect(href).toBe(
      "/discovery?similar=7&style_period=1&from=%2Fplaylists%2Fdetail%3Fid%3D3%26q%3Da+b",
    );
    expect(new URLSearchParams(href.split("?")[1]).get("from")).toBe(
      "/playlists/detail?id=3&q=a b",
    );
  });
});
