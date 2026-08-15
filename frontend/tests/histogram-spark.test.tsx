import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Histogram } from "@/components/dashboard/histogram";
import type { BpmBin } from "@/lib/api";

const BINS: BpmBin[] = [
  { from: 120, to: 124, count: 3 },
  { from: 124, to: 128, count: 9 },
  { from: 128, to: 132, count: 5 },
];

describe("histogram spark", () => {
  afterEach(cleanup);

  it("rende una barretta per bin, senza header né etichette min/max", () => {
    const { container } = render(<Histogram bins={BINS} variant="spark" />);
    const wrap = container.firstElementChild as HTMLElement;
    expect(wrap.getAttribute("aria-hidden")).toBe("true");
    expect(wrap.children.length).toBe(3);
    // Niente etichette BPM del rendering "full".
    expect(container.textContent).toBe("");
  });

  it("evidenzia il bin modale in fg, gli altri in faint", () => {
    const { container } = render(<Histogram bins={BINS} variant="spark" />);
    const bars = Array.from((container.firstElementChild as HTMLElement).children);
    expect(bars[1].className).toContain("bg-fg");
    expect(bars[0].className).toContain("bg-faint");
    expect(bars[2].className).toContain("bg-faint");
  });

  it("con bins vuoto non rende nulla (niente segnaposto nel colophon)", () => {
    const { container } = render(<Histogram bins={[]} variant="spark" />);
    expect(container.firstChild).toBeNull();
  });

  it("il rendering full resta invariato: barre interattive e range in calce", () => {
    const { container } = render(<Histogram bins={BINS} />);
    expect(container.querySelectorAll("button").length).toBe(3);
    expect(container.textContent).toContain("120");
    expect(container.textContent).toContain("132");
  });
});
