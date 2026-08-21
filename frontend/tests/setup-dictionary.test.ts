import { describe, expect, it } from "vitest";
import { it as dizionarioIt } from "@/lib/i18n/it";
import { en } from "@/lib/i18n/en";

/* Il dizionario e il registry del probe vivono ai due lati di un confine HTTP:
   niente li tiene allineati da solo. Questo test becca il caso che si verifica
   davvero — un componente tolto dal backend che lascia il suo testo qui — e
   non l'inverso: una chiave mancante degrada già da sola, perché la UI ripiega
   sul nome del componente (`?? c.key`). */
const COMPONENTI_VIVI = ["ffmpeg", "fpcalc", "slskd"];
const UNLOCKS_VIVI = [
  "audio_hash", "shazam", "soundcloud_download",
  "acoustid_fingerprint", "soulseek_download", "library_share",
];

describe("dizionario del wizard", () => {
  for (const [nome, d] of [["it", dizionarioIt], ["en", en]] as const) {
    it(`${nome}: nessuna descrizione di componenti che non esistono più`, () => {
      expect(Object.keys(d.setup.components).sort()).toEqual([...COMPONENTI_VIVI].sort());
    });

    it(`${nome}: nessuna voce unlocks orfana`, () => {
      expect(Object.keys(d.setup.unlocks).sort()).toEqual([...UNLOCKS_VIVI].sort());
    });
  }
});
