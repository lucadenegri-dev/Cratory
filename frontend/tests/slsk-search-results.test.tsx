import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SlskSearchResults } from "@/components/slsk-search-results";
import type { DownloadCandidate } from "@/lib/api";

afterEach(cleanup);

// I18nProvider di default e' "it" (stesso pattern di tests/wishlist-row.test.tsx).

function cand(i: number): DownloadCandidate {
  return {
    username: `user${i}`, filename: `Folder\\Track ${i}.flac`, size: 1000,
    bitrate: null, length: null, format: "flac", name_score: 0.9,
    quality_tier: 3, confidence: 0.9,
  };
}

const many = (n: number) => Array.from({ length: n }, (_, i) => cand(i + 1));

describe("SlskSearchResults", () => {
  it("mostra il conteggio totale dei risultati", () => {
    render(<SlskSearchResults results={many(3)} onGrab={vi.fn()} running={false} />);
    expect(screen.getByText("3 risultati")).toBeTruthy();
  });

  it("pagina da 40: prima pagina, poi Succ/Prec su TUTTI i risultati", () => {
    render(<SlskSearchResults results={many(85)} onGrab={vi.fn()} running={false} />);
    // prima pagina: 1–40, l'85° non e' visibile
    expect(screen.getByText("Track 1.flac")).toBeTruthy();
    expect(screen.queryByText("Track 41.flac")).toBeNull();
    expect(screen.getByText(/1–40/)).toBeTruthy();
    // seconda pagina
    fireEvent.click(screen.getByText("Succ"));
    expect(screen.getByText("Track 41.flac")).toBeTruthy();
    expect(screen.queryByText("Track 1.flac")).toBeNull();
    // terza e ultima pagina: coda oltre il vecchio cap di 40
    fireEvent.click(screen.getByText("Succ"));
    expect(screen.getByText("Track 85.flac")).toBeTruthy();
    expect(screen.getByText(/81–85/)).toBeTruthy();
    expect((screen.getByText("Succ").closest("button") as HTMLButtonElement).disabled).toBe(true);
    // indietro
    fireEvent.click(screen.getByText("Prec"));
    expect(screen.getByText("Track 41.flac")).toBeTruthy();
  });

  it("senza piu' pagine i controlli non compaiono", () => {
    render(<SlskSearchResults results={many(5)} onGrab={vi.fn()} running={false} />);
    expect(screen.queryByText("Succ")).toBeNull();
    expect(screen.queryByText("Prec")).toBeNull();
  });

  it("mostra il percorso della cartella oltre al nome file", () => {
    const c = { ...cand(1), filename: "Music\\Techno\\Classics\\Track 1.flac" };
    render(<SlskSearchResults results={[c]} onGrab={vi.fn()} running={false} />);
    expect(screen.getByText("Track 1.flac")).toBeTruthy();
    // Il path aiuta a giudicare il candidato (artista/release nella cartella):
    // separatori normalizzati a "/", senza il nome file ripetuto.
    expect(screen.getByText("Music/Techno/Classics")).toBeTruthy();
  });

  it("file senza cartelle: nessun path vuoto renderizzato", () => {
    const c = { ...cand(1), filename: "Track 1.flac" };
    const { container } = render(
      <SlskSearchResults results={[c]} onGrab={vi.fn()} running={false} />);
    expect(container.textContent).not.toContain("undefined");
    expect(screen.getByText("Track 1.flac")).toBeTruthy();
  });

  it("Scarica chiama onGrab col candidato giusto", () => {
    const onGrab = vi.fn();
    render(<SlskSearchResults results={many(2)} onGrab={onGrab} running={false} />);
    fireEvent.click(screen.getAllByText("Scarica")[1]);
    expect(onGrab).toHaveBeenCalledWith(expect.objectContaining({ username: "user2" }));
  });

  it("nuovi risultati riportano alla prima pagina", () => {
    const { rerender } = render(
      <SlskSearchResults results={many(85)} onGrab={vi.fn()} running={false} />);
    fireEvent.click(screen.getByText("Succ"));
    expect(screen.getByText("Track 41.flac")).toBeTruthy();
    rerender(<SlskSearchResults results={many(50)} onGrab={vi.fn()} running={false} />);
    expect(screen.getByText("Track 1.flac")).toBeTruthy();
    expect(screen.getByText(/1–40/)).toBeTruthy();
  });
});
