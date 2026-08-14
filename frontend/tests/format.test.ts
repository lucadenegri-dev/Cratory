import { afterEach, describe, expect, it, vi } from "vitest";
import { fmtDate, fmtDateShort, fmtSize, trackLabel } from "@/lib/api/format";
import { setCurrentLanguage } from "@/lib/i18n/runtime";
import type { Track } from "@/lib/api/types";

afterEach(() => {
  // I test cambiano la lingua attiva globale (stato fuori-React in lib/i18n/runtime.ts):
  // va ripristinata per non far trapelare "en" negli altri test del file.
  setCurrentLanguage("it");
});

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

describe("fmtDate", () => {
  // Data fissa nota: 5 marzo 2026. Con month:"short" i-IT ed en-GB divergono
  // in modo stabile (case del mese: "mar" minuscolo vs "Mar" maiuscolo, oltre
  // al nome stesso quando il mese non e' un prestito come "mar"/"Mar") — a
  // differenza del formato 2-digit di fmtDateShort (vedi sotto), che coincide
  // fra le due locali per costruzione CLDR e va quindi verificato sull'argomento
  // locale passato a toLocaleDateString, non sulla stringa risultante.
  const iso = "2026-03-05T12:00:00Z";

  it("in italiano usa la locale it-IT (mese abbreviato minuscolo)", () => {
    setCurrentLanguage("it");
    expect(fmtDate(iso)).toBe("05 mar 2026");
  });

  it("in inglese usa la locale en-GB, non it-IT a prescindere dalla lingua", () => {
    setCurrentLanguage("en");
    expect(fmtDate(iso)).toBe("05 Mar 2026");
  });

  it("le due lingue producono output diversi per la stessa data", () => {
    setCurrentLanguage("it");
    const itOut = fmtDate(iso);
    setCurrentLanguage("en");
    const enOut = fmtDate(iso);
    expect(itOut).not.toBe(enOut);
  });
});

describe("fmtDateShort", () => {
  // day/month "2-digit" produce la STESSA stringa in it-IT ed en-GB per
  // costruzione (entrambe dd/mm/yy): un confronto sull'output non
  // distinguerebbe "cablato su it-IT" da "guidato dalla lingua attiva ma
  // scelta en-GB". Si verifica quindi l'argomento locale passato a
  // toLocaleDateString, che e' cio' che il bug sbagliava davvero.
  const iso = "2026-03-05T12:00:00Z";

  it("passa la locale it-IT quando la lingua attiva e' it", () => {
    const spy = vi.spyOn(Date.prototype, "toLocaleDateString");
    try {
      setCurrentLanguage("it");
      fmtDateShort(iso);
      expect(spy).toHaveBeenCalledWith("it-IT", expect.anything());
    } finally {
      // In un finally: se l'expect sopra fallisce, lo spy va comunque
      // ripristinato, altrimenti resta attivo per il resto del file e
      // confonde la diagnosi del test successivo.
      spy.mockRestore();
    }
  });

  it("passa la locale en-GB quando la lingua attiva e' en (non it-IT fisso)", () => {
    const spy = vi.spyOn(Date.prototype, "toLocaleDateString");
    try {
      setCurrentLanguage("en");
      fmtDateShort(iso);
      expect(spy).toHaveBeenCalledWith("en-GB", expect.anything());
    } finally {
      spy.mockRestore();
    }
  });

  it("il valore di ritorno resta dd/mm/yy in entrambe le lingue (nessuna regressione visiva)", () => {
    setCurrentLanguage("it");
    expect(fmtDateShort(iso)).toBe("05/03/26");
    setCurrentLanguage("en");
    expect(fmtDateShort(iso)).toBe("05/03/26");
  });
});

describe("trackLabel", () => {
  const withValues = { artist: "Marco Faraone", title: "Real Freak" } as unknown as Track;
  const withoutValues = { artist: null, title: null } as unknown as Track;

  it("con artista/titolo presenti e' identico nelle due lingue", () => {
    setCurrentLanguage("it");
    expect(trackLabel(withValues)).toBe("Marco Faraone — Real Freak");
    setCurrentLanguage("en");
    expect(trackLabel(withValues)).toBe("Marco Faraone — Real Freak");
  });

  it("in italiano il fallback e' 'Artista sconosciuto' / 'Senza titolo'", () => {
    setCurrentLanguage("it");
    expect(trackLabel(withoutValues)).toBe("Artista sconosciuto — Senza titolo");
  });

  it("in inglese il fallback e' 'Unknown artist' / 'Untitled', non l'italiano", () => {
    setCurrentLanguage("en");
    expect(trackLabel(withoutValues)).toBe("Unknown artist — Untitled");
  });
});
