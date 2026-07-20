import { describe, expect, it } from "vitest";

import { pickSurprise } from "@/lib/discovery-surprise";

// RNG deterministico: restituisce in sequenza i valori dati, poi 0.
function seqRng(values: number[]): () => number {
  let i = 0;
  return () => (i < values.length ? values[i++] : 0);
}

describe("pickSurprise", () => {
  const POOL = { genres: ["Acid House", "Techno"], labels: ["Trax Records"] };

  it("pool vuoto -> null", () => {
    expect(pickSurprise({ genres: [], labels: [] }, null)).toBeNull();
  });

  it("pick uniforme deterministico con RNG fisso: primo elemento + prima depth", () => {
    // rng[0]=0 -> indice 0 del pool unito (generi prima): "Acid House".
    // rng[1]=0 -> prima depth: 0.0.
    const pick = pickSurprise(POOL, null, seqRng([0, 0]));
    expect(pick).toEqual({ seedType: "genre", value: "Acid House", depth: 0.0 });
  });

  it("il seedType segue il gruppo di provenienza (label)", () => {
    // 3 elementi uniti: [Acid House(genre), Techno(genre), Trax Records(label)].
    // rng appena sotto 1 -> ultimo indice -> la label.
    const pick = pickSurprise(POOL, null, seqRng([0.99, 0.5]));
    expect(pick).toEqual({ seedType: "label", value: "Trax Records", depth: 0.5 });
  });

  it("depth uniforme sui tre valori", () => {
    expect(pickSurprise(POOL, null, seqRng([0, 0.99]))?.depth).toBe(1.0);
    expect(pickSurprise(POOL, null, seqRng([0, 0.5]))?.depth).toBe(0.5);
  });

  it("anti-ripetizione: esclude il seme corrente (case-insensitive)", () => {
    // current = "acid house": resta [Techno, Trax Records]. rng=0 -> Techno.
    const pick = pickSurprise(POOL, "acid house", seqRng([0, 0]));
    expect(pick?.value).toBe("Techno");
  });

  it("unico seme uguale a current: ripesca quello invece di null", () => {
    const pick = pickSurprise({ genres: ["Techno"], labels: [] }, "Techno", seqRng([0, 0]));
    expect(pick).toEqual({ seedType: "genre", value: "Techno", depth: 0.0 });
  });
});
