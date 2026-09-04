import { describe, expect, it } from "vitest";

import { personaFor } from "@/lib/persona";

/* L'easter egg si accende su un solo username. Il denominatore è il caso
   positivo: senza, ogni "cratory" sarebbe verde anche con la funzione vuota. */
describe("personaFor", () => {
  it("xgiorgix accende la persona goodgirl, in qualunque maiuscola", () => {
    expect(personaFor("xgiorgix")).toBe("goodgirl");
    expect(personaFor("XGIORGIX")).toBe("goodgirl");
  });

  it("tutto il resto è cratory", () => {
    expect(personaFor(null)).toBe("cratory");
    expect(personaFor(undefined)).toBe("cratory");
    expect(personaFor("")).toBe("cratory");
    expect(personaFor("giorgia")).toBe("cratory");
    expect(personaFor("xgiorgix2")).toBe("cratory");
  });
});
