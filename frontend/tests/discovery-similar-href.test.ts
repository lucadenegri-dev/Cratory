import { describe, expect, it } from "vitest";
import { similarHref } from "@/lib/discovery-dig";

describe("similarHref", () => {
  it("porta l'id della traccia e l'interruttore spento", () => {
    expect(similarHref(42, false)).toBe("/discovery?similar=42&style_period=0");
  });

  it("accende l'interruttore nell'URL", () => {
    expect(similarHref(42, true)).toBe("/discovery?similar=42&style_period=1");
  });
});
