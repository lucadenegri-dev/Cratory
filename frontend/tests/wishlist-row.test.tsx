import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { WishlistRow } from "@/components/wishlist-row";
import type { Track } from "@/lib/api";

afterEach(cleanup);

// I18nProvider di default e' "it" (vedi lib/i18n/index.tsx): il valore di default
// del context espone gia' t: it, quindi useT() funziona senza wrapper nei test
// (stesso pattern di tests/analysis-page.test.tsx, che non avvolge nessun provider).

const base = {
  id: 1, title: "Real Freak", artist: "Marco Faraone",
  playlists: [{ id: 7, name: "Techno Peak" }, { id: 9, name: "Scoperte" }],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
} as unknown as Track;

const noop = { onDownload: vi.fn(), onSearch: vi.fn(), onLinkFile: vi.fn(), onClearOutcome: vi.fn(), onArchive: vi.fn(), onRestore: vi.fn() };

// Valore realistico di `from` come lo calcola WishlistInner (path + query dei
// filtri vivi, vedi app/wishlist/page.tsx): la riga non lo ricostruisce piu' da
// usePathname(), lo riceve come prop.
const from = "/wishlist?tab=not_found&q=aphex";

describe("WishlistRow", () => {
  it("mostra label, chip playlist e badge 'mai tentata'", () => {
    render(<WishlistRow track={base} downloadsAvailable from={from} {...noop} />);
    expect(screen.getByText("Marco Faraone — Real Freak")).toBeTruthy();
    // `from` arriva come prop (path + query dei filtri correnti della wishlist):
    // l'href deve portare l'origine esatta, codificata per intero (query compresa).
    expect(screen.getByText("Techno Peak").closest("a")?.getAttribute("href"))
      .toBe("/playlists/7?from=%2Fwishlist%3Ftab%3Dnot_found%26q%3Daphex");
    expect(screen.getByText("Scoperte").closest("a")?.getAttribute("href"))
      .toBe("/playlists/9?from=%2Fwishlist%3Ftab%3Dnot_found%26q%3Daphex");
    expect(screen.getByText("mai tentata")).toBeTruthy();
  });

  it("azione primaria contestuale: Scarica se mai tentata, Riprova se non trovata, Rivedi se in review", () => {
    const { rerender } = render(<WishlistRow track={base} downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByText("Scarica"));
    expect(noop.onDownload).toHaveBeenCalled();
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "not_found" } as Track} downloadsAvailable from={from} {...noop} />);
    expect(screen.getByText("Riprova")).toBeTruthy();
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "needs_review" } as Track} downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByText("Rivedi"));
    expect(noop.onSearch).toHaveBeenCalled();
  });

  it("scaricata-non-collegata: primaria = Collega file", () => {
    render(<WishlistRow track={{ ...base, last_download_outcome: "downloaded" } as Track} downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByText("Collega file"));
    expect(noop.onLinkFile).toHaveBeenCalled();
  });

  it("downloadsAvailable=false disabilita solo il download, Compra resta attivo", () => {
    render(<WishlistRow track={base} downloadsAvailable={false} from={from} {...noop} />);
    expect((screen.getByText("Scarica").closest("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Compra"));
    expect(screen.getByText("Bandcamp").closest("a")?.getAttribute("href"))
      .toBe("https://bandcamp.com/search?q=Marco%20Faraone%20Real%20Freak");
  });

  // La wishlist carica solo tracce con has_local_file=false, quindi trackCoverSrc
  // può usare unicamente album_art_url (Spotify): il ramo "artwork embedded dal
  // file" non si attiva mai e non parte nessuna richiesta a /api/tracks/{id}/cover.
  it("mostra la cover Spotify quando c'e', altrimenti il placeholder", () => {
    const { container, rerender } = render(
      <WishlistRow track={{ ...base, album_art_url: "https://i.scdn.co/image/abc", has_local_file: false } as Track}
        downloadsAvailable from={from} {...noop} />,
    );
    expect(container.querySelector("img")?.getAttribute("src")).toBe("https://i.scdn.co/image/abc");

    rerender(
      <WishlistRow track={{ ...base, album_art_url: null, has_local_file: false } as Track}
        downloadsAvailable from={from} {...noop} />,
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("vista archiviata: solo Ripristina e Compra", () => {
    render(<WishlistRow track={base} archived downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByText("Ripristina"));
    expect(noop.onRestore).toHaveBeenCalled();
    expect(screen.queryByText("Scarica")).toBeNull();
  });

  it("menu …: «Cerca su Soulseek» disponibile per ogni stato e chiama onSearch", () => {
    render(<WishlistRow track={base} downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByLabelText("Altre azioni"));
    fireEvent.click(screen.getByText("Cerca su Soulseek"));
    expect(noop.onSearch).toHaveBeenCalled();
  });

  it("la checkbox compare solo con onToggleSelect e riporta la selezione", () => {
    const onToggleSelect = vi.fn();
    const { rerender, container } = render(
      <WishlistRow track={base} downloadsAvailable from={from} {...noop} />);
    expect(container.querySelector('input[type="checkbox"]')).toBeNull();

    rerender(<WishlistRow track={base} downloadsAvailable from={from} {...noop}
      selected onToggleSelect={onToggleSelect} />);
    const box = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    expect(onToggleSelect).toHaveBeenCalled();
  });
});
