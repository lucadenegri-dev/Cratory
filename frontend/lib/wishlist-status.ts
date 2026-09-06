// Stato wishlist di una traccia non posseduta, derivato dall'ultimo esito
// download. "downloaded" qui significa "scaricata ma non collegata" (in
// wishlist has_local_file e' per definizione false): caso limite della spec,
// nel filtro conta sotto "review".

export type WishlistStatus = "never" | "review" | "not_found" | "failed" | "downloaded_unlinked";
export type WishlistTab = "never" | "review" | "not_found" | "failed" | "queued";

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

// Stato della riga ai fini del filtro: la coda prevale sull'ultimo esito, come
// fa la riga quando sceglie cosa scrivere in colonna (wishlist-row.tsx). Una
// funzione sola per il conteggio delle tab e per il filtro della lista: se
// divergessero, una tab direbbe "3" e la lista ne mostrerebbe due.
export function rowTab(t: { last_download_outcome: string | null }, queued: boolean): WishlistTab {
  return queued ? "queued" : statusTab(wishlistStatus(t));
}

// "In coda" non e' un WishlistStatus: `last_download_outcome` racconta l'ultimo
// esito, la coda racconta il presente, e i due convivono (una "non trovata"
// riaccodata resta "non trovata" finche' il nuovo giro non finisce). La riga
// li sovrappone: se la traccia e' in coda, mostra quello. queued e running
// sono entrambi "in coda" per chi guarda la wishlist.
export function queuedTrackIds(items: readonly { track_id: number; state: string }[]): Set<number> {
  const ids = new Set<number>();
  for (const it of items) if (it.state === "queued" || it.state === "running") ids.add(it.track_id);
  return ids;
}
