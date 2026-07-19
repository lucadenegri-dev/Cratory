// Stato wishlist di una traccia non posseduta, derivato dall'ultimo esito
// download. "downloaded" qui significa "scaricata ma non collegata" (in
// wishlist has_local_file e' per definizione false): caso limite della spec,
// nel filtro conta sotto "review".

export type WishlistStatus = "never" | "review" | "not_found" | "failed" | "downloaded_unlinked";
export type WishlistTab = "never" | "review" | "not_found" | "failed";

export function wishlistStatus(t: { last_download_outcome: string | null }): WishlistStatus {
  switch (t.last_download_outcome) {
    case "needs_review": return "review";
    case "not_found": return "not_found";
    case "failed": return "failed";
    case "downloaded": return "downloaded_unlinked";
    default: return "never";
  }
}

export function statusTab(s: WishlistStatus): WishlistTab {
  return s === "downloaded_unlinked" ? "review" : s;
}
