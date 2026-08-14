import { describe, expect, it } from "vitest";
import { sourceLabel } from "@/lib/track-source";
import { en } from "@/lib/i18n/en";
import { it as itDict } from "@/lib/i18n/it";

describe("sourceLabel", () => {
  it("mappa library/downloads sulle etichette del dizionario attivo (EN)", () => {
    expect(sourceLabel(en)).toEqual({ library: "library", downloads: "downloads" });
  });

  it("mappa library/downloads sulle etichette del dizionario attivo (IT)", () => {
    expect(sourceLabel(itDict)).toEqual({ library: "libreria", downloads: "download" });
  });
});
