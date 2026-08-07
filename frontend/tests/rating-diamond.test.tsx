import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RatingDiamond } from "@/components/rating-diamond";

const updateTrack = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updateTrack: (...args: unknown[]) => updateTrack(...args),
}));

afterEach(() => {
  cleanup();
  updateTrack.mockClear();
});

describe("RatingDiamond", () => {
  it("chiuso mostra solo il rombo dello stato corrente", () => {
    render(<RatingDiamond trackId={1} rating={null} />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("il click apre i 3 livelli", async () => {
    render(<RatingDiamond trackId={1} rating={null} />);
    await act(async () => {
      screen.getByRole("button").click();
    });
    expect(screen.getAllByRole("button")).toHaveLength(4); // 3 livelli + toggle
  });

  it("scegliere un livello chiama la PATCH col valore giusto", async () => {
    render(<RatingDiamond trackId={7} rating={null} />);
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle("Vota 2 su 3"));
    });
    expect(updateTrack).toHaveBeenCalledWith(7, { rating: 2 });
  });

  it("ri-cliccare il livello attivo toglie il voto", async () => {
    render(<RatingDiamond trackId={7} rating={2} />);
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle("Vota 2 su 3"));
    });
    expect(updateTrack).toHaveBeenCalledWith(7, { rating: null });
  });

  it("se la PATCH fallisce lo stato torna indietro", async () => {
    updateTrack.mockRejectedValueOnce(new Error("boom"));
    const { container } = render(<RatingDiamond trackId={7} rating={null} />);
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle("Vota 3 su 3"));
    });
    expect(updateTrack).toHaveBeenCalledWith(7, { rating: 3 });
    // il pannello si chiude subito (ottimistico); dopo il rollback il rombo
    // torna "non votata": un solo bottone e nessun fill sul poligono.
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(container.querySelector("polygon")?.getAttribute("fill")).toBe("none");
  });
});
