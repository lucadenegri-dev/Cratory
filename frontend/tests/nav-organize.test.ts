import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const nav = readFileSync(resolve(__dirname, "../components/index-nav.tsx"), "utf8");

describe("gruppo Organize nella nav", () => {
  it("elenca le cinque pagine di Organize", () => {
    /* Cinque, non le quattro del design doc: /organize è solo un redirect a
       /organize/files, e le pagine reali sono quelle che il menu di Organize
       elencava prima di essere assorbito. */
    for (const href of ["/organize/files", "/organize/issues", "/organize/duplicates",
      "/organize/plan", "/organize/history"]) {
      expect(nav).toContain(`"${href}"`);
    }
  });

  it("non mette in menu /organize, che è solo un redirect", () => {
    expect(nav).not.toMatch(/href: "\/organize"/);
  });

  it("non mette in menu le impostazioni di Organize, che sono in /settings", () => {
    expect(nav).not.toContain('"/organize/settings"');
  });

  it("il gruppo sta fra Scopri e Colleziona", () => {
    const i = (s: string) => nav.indexOf(s);
    expect(i("groupDiscover")).toBeGreaterThan(-1);
    expect(i("groupDiscover")).toBeLessThan(i("groupOrganize"));
    expect(i("groupOrganize")).toBeLessThan(i("groupCollect"));
  });
});
