import { describe, expect, it } from "vitest";
import { statusTab, wishlistStatus } from "@/lib/wishlist-status";

describe("wishlistStatus", () => {
  it("mappa gli esiti download", () => {
    expect(wishlistStatus({ last_download_outcome: null })).toBe("never");
    expect(wishlistStatus({ last_download_outcome: "needs_review" })).toBe("review");
    expect(wishlistStatus({ last_download_outcome: "not_found" })).toBe("not_found");
    expect(wishlistStatus({ last_download_outcome: "failed" })).toBe("failed");
    // In wishlist has_local_file e' sempre false: un esito "downloaded" senza
    // file e' il caso limite della spec.
    expect(wishlistStatus({ last_download_outcome: "downloaded" })).toBe("downloaded_unlinked");
  });
  it("esiti sconosciuti non rompono: trattati come mai tentata", () => {
    expect(wishlistStatus({ last_download_outcome: "boh" })).toBe("never");
  });
});

describe("statusTab", () => {
  it("downloaded_unlinked conta sotto review", () => {
    expect(statusTab("downloaded_unlinked")).toBe("review");
    expect(statusTab("never")).toBe("never");
    expect(statusTab("not_found")).toBe("not_found");
    expect(statusTab("failed")).toBe("failed");
    expect(statusTab("review")).toBe("review");
  });
});

// Stato "in coda": non viene da `last_download_outcome` (che racconta l'ultimo
// esito, non il presente) ma dallo snapshot della coda. queued e running sono
// entrambi "in coda" per la wishlist; done/cancelled no.
import { queuedTrackIds } from "@/lib/wishlist-status";

describe("queuedTrackIds", () => {
  it("raccoglie solo gli item in attesa o in corso", () => {
    const ids = queuedTrackIds([
      { track_id: 1, state: "queued" },
      { track_id: 2, state: "running" },
      { track_id: 3, state: "done" },
      { track_id: 4, state: "cancelled" },
    ]);
    expect([...ids].sort()).toEqual([1, 2]);
  });
});

// La coda vince sull'ultimo esito: una "non trovata" riaccodata conta (e si
// filtra) come "in coda", cosi' la tab e la riga dicono la stessa cosa.
import { rowTab } from "@/lib/wishlist-status";

describe("rowTab", () => {
  it("in coda prevale sull'esito precedente", () => {
    expect(rowTab({ last_download_outcome: "not_found" }, true)).toBe("queued");
    expect(rowTab({ last_download_outcome: "not_found" }, false)).toBe("not_found");
    expect(rowTab({ last_download_outcome: "downloaded" }, false)).toBe("review");
    expect(rowTab({ last_download_outcome: null }, false)).toBe("never");
  });
});
