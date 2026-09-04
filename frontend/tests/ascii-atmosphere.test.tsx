import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  AsciiAtmosphere, airParticles, HEART, HEART_GLYPHS,
} from "@/components/dashboard/ascii-atmosphere";

/* I cuori dell'easter egg (spec 2026-09-04) stanno nel pulviscolo, che si vede
   solo mentre suona. La tavolozza di default è il denominatore: senza, un
   campo fatto tutto di cuori passerebbe il test sui cuori. */
describe("airParticles", () => {
  it("la tavolozza di default non ha cuori; quella dell'easter egg ne ha un terzo", () => {
    expect(airParticles(120).some((p) => p.glyph === HEART)).toBe(false);
    const hearts = airParticles(120, 0, HEART_GLYPHS).filter((p) => p.glyph === HEART).length;
    expect(hearts).toBeGreaterThan(20);
    expect(hearts).toBeLessThan(60);
  });

  it("cambiare tavolozza non sposta le particelle: stesse posizioni e corse", () => {
    const plain = airParticles(120);
    const loving = airParticles(120, 0, HEART_GLYPHS);
    for (let i = 0; i < plain.length; i++) {
      expect(loving[i].left).toBe(plain[i].left);
      expect(loving[i].duration).toBe(plain[i].duration);
      expect(loving[i].delay).toBe(plain[i].delay);
    }
  });
});

describe("AsciiAtmosphere", () => {
  afterEach(cleanup);

  it("con hearts i cuori sono in pagina, in danger; senza, nessuno", () => {
    const { container } = render(<AsciiAtmosphere active hearts />);
    const hearts = [...container.querySelectorAll("span")].filter((s) => s.textContent === HEART);
    expect(hearts.length).toBeGreaterThan(0);
    for (const h of hearts) expect(h.className).toContain("air-heart");

    cleanup();
    const plain = render(<AsciiAtmosphere active />).container;
    expect([...plain.querySelectorAll("span")].some((s) => s.textContent === HEART)).toBe(false);
    expect(plain.querySelectorAll(".air-heart").length).toBe(0);
  });
});
