import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve, join } from "node:path";

// Le pagine sotto app/organize (e i componenti condivisi sotto components/organize)
// sono state spostate da / a /organize/*. Ogni redirect programmatica
// (redirect(...) / router.push(...) / router.replace(...)) e ogni href statico
// (JSX <Link href="..."> o oggetti tipo `{ href: "/files" }` usati per costruire
// la nav) verso un path assoluto deve restare dentro /organize/, altrimenti
// punta a rotte ormai inesistenti (es. /files invece di /organize/files).

const organizeDirs = [
  resolve(__dirname, "../app/organize"),
  resolve(__dirname, "../components/organize"),
];

function collectTsxFiles(dir: string): string[] {
  return readdirSync(dir, { recursive: true })
    .map((entry) => entry.toString())
    .filter((entry) => entry.endsWith(".tsx") || entry.endsWith(".ts"))
    .map((entry) => join(dir, entry));
}

const redirectCallRegex = /(?:redirect|router\.(?:push|replace))\(\s*[`"']([^`"']+)[`"']/g;
// Copre sia l'attributo JSX (href="/x") sia la property di un letterale
// oggetto (href: "/x", come nell'array NAV di index-nav.tsx).
const hrefRegex = /href\s*[:=]\s*[`"']([^`"']+)[`"']/g;

describe("redirect e href statiche sotto app/organize e components/organize", () => {
  it("puntano tutte a path prefissati con /organize/", () => {
    const offenders: string[] = [];

    for (const dir of organizeDirs) {
      for (const file of collectTsxFiles(dir)) {
        const source = readFileSync(file, "utf8");
        for (const regex of [redirectCallRegex, hrefRegex]) {
          for (const match of source.matchAll(regex)) {
            const target = match[1];
            if (target.startsWith("/") && !target.startsWith("/organize/")) {
              offenders.push(`${file}: ${match[0]}`);
            }
          }
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
