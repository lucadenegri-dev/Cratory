import { describe, expect, it } from "vitest";
import { fmtSize } from "@/lib/api/format";

describe("fmtSize", () => {
  it("converte i byte in MB con una cifra decimale", () => {
    expect(fmtSize(1024 * 1024)).toBe("1.0 MB");
    expect(fmtSize(5 * 1024 * 1024)).toBe("5.0 MB");
    // 1.5 MB esatti: verifica l'arrotondamento a una cifra decimale.
    expect(fmtSize(1.5 * 1024 * 1024)).toBe("1.5 MB");
    // Non un multiplo tondo: verifica che arrotondi, non tronchi.
    expect(fmtSize(1234567)).toBe("1.2 MB");
  });

  it("i byte falsy tornano stringa vuota, non '0.0 MB'", () => {
    expect(fmtSize(0)).toBe("");
    expect(fmtSize(null)).toBe("");
  });
});
