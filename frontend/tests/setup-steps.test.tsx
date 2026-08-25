import { describe, expect, it } from "vitest";
import { passiDelWizard } from "@/lib/setup-steps";

/* Il passo dei prerequisiti esiste per far installare qualcosa. Quando non
   c'è niente da installare — l'app impacchettata porta i binari con sé — non
   ha ragione di esistere, e il contatore "passo N di M" deve restare onesto
   invece di saltare un numero. */

const daBundle = [
  { present: true, source: "bundle" },
  { present: true, source: "bundle" },
];

describe("passi del wizard", () => {
  it("nel bundle sono quattro e i prerequisiti non ci sono", () => {
    expect(passiDelWizard(daBundle)).toEqual(["welcome", "library", "services", "summary"]);
  });

  it("da checkout restano cinque", () => {
    const passi = passiDelWizard([
      { present: true, source: "path" },
      { present: false, source: null },
    ]);
    expect(passi).toContain("prerequisites");
    expect(passi).toHaveLength(5);
  });

  it("un solo componente non dal bundle basta a tenere il passo", () => {
    expect(
      passiDelWizard([
        { present: true, source: "bundle" },
        { present: true, source: "path" },
      ]),
    ).toContain("prerequisites");
  });

  it("finché il probe non ha risposto il passo resta", () => {
    // Toglierlo e rimetterlo mentre l'utente guarda sarebbe peggio che
    // mostrarlo un istante di troppo.
    expect(passiDelWizard(null)).toContain("prerequisites");
  });

  it("un probe vuoto non fa sparire il passo", () => {
    // `every` su una lista vuota è vero: senza il controllo sulla lunghezza,
    // un probe che non ha restituito componenti nasconderebbe il passo
    // proprio quando non sappiamo niente.
    expect(passiDelWizard([])).toContain("prerequisites");
  });
});
