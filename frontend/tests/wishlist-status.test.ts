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
