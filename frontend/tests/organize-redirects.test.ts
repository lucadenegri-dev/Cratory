import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve, join } from "node:path";

// Le pagine sotto app/organize sono state spostate da / a /organize/*.
// Ogni redirect programmatica (redirect(...) / router.push(...) / router.replace(...))
// verso un path assoluto deve restare dentro /organize/, altrimenti punta a rotte
// ormai inesistenti (es. /files invece di /organize/files) e nessun grep sugli
// href se ne accorge.

const organizeDir = resolve(__dirname, "../app/organize");

function collectTsxFiles(dir: string): string[] {
  return readdirSync(dir, { recursive: true })
    .map((entry) => entry.toString())
    .filter((entry) => entry.endsWith(".tsx") || entry.endsWith(".ts"))
    .map((entry) => join(dir, entry));
}

const redirectCallRegex = /(?:redirect|router\.(?:push|replace))\(\s*[`"']([^`"']+)[`"']/g;

describe("redirect programmatiche sotto app/organize", () => {
  it("puntano tutte a path prefissati con /organize/", () => {
    const offenders: string[] = [];

    for (const file of collectTsxFiles(organizeDir)) {
      const source = readFileSync(file, "utf8");
      for (const match of source.matchAll(redirectCallRegex)) {
        const target = match[1];
        if (target.startsWith("/") && !target.startsWith("/organize/")) {
          offenders.push(`${file}: ${match[0]}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
