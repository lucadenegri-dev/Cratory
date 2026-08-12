import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

describe("il cluster shell di Organize non esiste più", () => {
  for (const c of ["editorial-shell", "index-nav", "clock", "theme-toggle"]) {
    it(`components/organize/${c}.tsx è stato rimosso`, () => {
      expect(existsSync(resolve(__dirname, `../components/organize/${c}.tsx`))).toBe(false);
    });
  }
});
