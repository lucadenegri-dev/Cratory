import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { en } from "../lib/i18n/en";
import { it as itDict } from "../lib/i18n/it";

const nav = readFileSync(resolve(__dirname, "../components/index-nav.tsx"), "utf8");
const jobs = readFileSync(resolve(__dirname, "../components/jobs-provider.tsx"), "utf8");

/* La pagina /downloads è esistita per un po' senza che nulla la linkasse: la
   voce di menu puntava a /wishlist e così anche la riga della barra dei job,
   quindi ci si arrivava solo digitando l'URL. Questi test tengono la rotta
   agganciata a qualcosa di cliccabile. */
describe("la coda dei download è raggiungibile", () => {
  it("il menu ha una voce che porta a /downloads", () => {
    expect(nav).toContain('href: "/downloads"');
  });

  it("la voce della coda è distinta da quella della wishlist", () => {
    expect(nav).toContain('href: "/wishlist"');
    expect(nav).toContain("t.nav.queue");
    expect(itDict.nav.queue).not.toBe(itDict.nav.downloads);
    expect(en.nav.queue).not.toBe(en.nav.downloads);
  });

  it("l'etichetta esiste in entrambi i dizionari", () => {
    expect(itDict.nav.queue).toBeTruthy();
    expect(en.nav.queue).toBeTruthy();
  });

  it("la riga della barra dei job porta alla coda, non alla wishlist", () => {
    // La riga "download" è l'unica della barra che nomina soulseekDownload:
    // si ritaglia il suo blocco per non leggere l'href di un altro job.
    const start = jobs.indexOf("t.jobs.soulseekDownload");
    expect(start).toBeGreaterThan(-1);
    const block = jobs.slice(start, start + 400);
    expect(block).toContain('href: "/downloads"');
    expect(block).not.toContain('href: "/wishlist"');
  });
});
