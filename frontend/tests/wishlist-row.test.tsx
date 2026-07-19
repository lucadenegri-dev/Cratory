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

const noop = { onDownload: vi.fn(), onReview: vi.fn(), onLinkFile: vi.fn(), onClearOutcome: vi.fn(), onArchive: vi.fn(), onRestore: vi.fn() };

describe("WishlistRow", () => {
  it("mostra label, chip playlist e badge 'mai tentata'", () => {
    render(<WishlistRow track={base} downloadsAvailable {...noop} />);
    expect(screen.getByText("Marco Faraone — Real Freak")).toBeTruthy();
    expect(screen.getByText("Techno Peak").closest("a")?.getAttribute("href")).toBe("/playlists/7");
    expect(screen.getByText("Scoperte").closest("a")?.getAttribute("href")).toBe("/playlists/9");
    expect(screen.getByText("mai tentata")).toBeTruthy();
  });

  it("azione primaria contestuale: Scarica se mai tentata, Riprova se non trovata, Rivedi se in review", () => {
    const { rerender } = render(<WishlistRow track={base} downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Scarica"));
    expect(noop.onDownload).toHaveBeenCalled();
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "not_found" } as Track} downloadsAvailable {...noop} />);
    expect(screen.getByText("Riprova")).toBeTruthy();
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "needs_review" } as Track} downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Rivedi"));
    expect(noop.onReview).toHaveBeenCalled();
  });

  it("scaricata-non-collegata: primaria = Collega file", () => {
    render(<WishlistRow track={{ ...base, last_download_outcome: "downloaded" } as Track} downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Collega file"));
    expect(noop.onLinkFile).toHaveBeenCalled();
  });

  it("downloadsAvailable=false disabilita solo il download, Compra resta attivo", () => {
    render(<WishlistRow track={base} downloadsAvailable={false} {...noop} />);
    expect((screen.getByText("Scarica").closest("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Compra"));
    expect(screen.getByText("Bandcamp").closest("a")?.getAttribute("href"))
      .toBe("https://bandcamp.com/search?q=Marco%20Faraone%20Real%20Freak");
  });

  it("vista archiviata: solo Ripristina e Compra", () => {
    render(<WishlistRow track={base} archived downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Ripristina"));
    expect(noop.onRestore).toHaveBeenCalled();
    expect(screen.queryByText("Scarica")).toBeNull();
  });
});
