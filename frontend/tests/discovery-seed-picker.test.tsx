import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { DiscoverySeedPicker } from "@/components/discovery-seed-picker";
import type { DigSeed } from "@/lib/discovery-seeds";

afterEach(cleanup);

const OPTIONS = {
  genres: { library: ["Acid House", "Techno"], styles: ["Deep House", "Acid House"] },
  labels: ["Trax Records"],
  genreCounts: [{ genre: "Techno", count: 388 }, { genre: "Acid House", count: 41 }],
};
const DEEP: DigSeed = { type: "genre", value: "Deep House" };

function setup(seeds: DigSeed[] = [], over: Partial<React.ComponentProps<typeof DiscoverySeedPicker>> = {}) {
  const onChange = vi.fn();
  render(<DiscoverySeedPicker seeds={seeds} onChange={onChange} options={OPTIONS} {...over} />);
  return onChange;
}

const input = () => screen.getByRole("combobox") as HTMLInputElement;

describe("DiscoverySeedPicker", () => {
  it("rende i semi come chip con l'azione di rimozione", () => {
    const onChange = setup([DEEP, { type: "label", value: "Trax Records" }]);
    fireEvent.click(screen.getByLabelText("Togli Deep House"));
    expect(onChange).toHaveBeenCalledWith([{ type: "label", value: "Trax Records" }]);
  });

  it("scegliere dal menu aggiunge col tipo del gruppo", () => {
    const onChange = setup([DEEP]);
    fireEvent.focus(input());
    fireEvent.mouseDown(screen.getByText("Trax Records"));
    expect(onChange).toHaveBeenCalledWith([DEEP, { type: "label", value: "Trax Records" }]);
  });

  it("Invio sul testo libero aggiunge un GENERE e svuota il campo", () => {
    const onChange = setup([]);
    fireEvent.change(input(), { target: { value: "Inventato" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith([{ type: "genre", value: "Inventato" }]);
    expect(input().value).toBe("");
  });

  it("un duplicato non entra: il chip esistente lampeggia", () => {
    const onChange = setup([DEEP]);
    fireEvent.change(input(), { target: { value: "deep house" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Deep House").closest("[data-flash]")).toBeTruthy();
  });

  it("al cap il campo è disabilitato e lo spiega", () => {
    const four = Array.from({ length: 4 }, (_, i) => ({ type: "genre" as const, value: `G${i}` }));
    setup(four);
    expect(input().disabled).toBe(true);
    expect(screen.getByText("Al massimo 4 semi per scavo")).toBeTruthy();
  });

  it("la tavolozza mostra i generi in libreria col conteggio, poi gli stili senza doppioni", () => {
    setup([]);
    const lib = screen.getByText("In libreria").parentElement!;
    expect(lib.textContent).toContain("Techno");
    expect(lib.textContent).toContain("388");
    const styles = screen.getByText("Altri stili").parentElement!;
    expect(styles.textContent).toContain("Deep House");
    expect(styles.textContent).not.toContain("Acid House");   // già in libreria
  });

  it("un chip della tavolozza commuta il seme nei due versi", () => {
    const onChange = setup([]);
    fireEvent.click(screen.getByRole("button", { name: /^Techno/ }));
    expect(onChange).toHaveBeenLastCalledWith([{ type: "genre", value: "Techno" }]);
    cleanup();
    const onChange2 = setup([{ type: "genre", value: "Techno" }]);
    fireEvent.click(screen.getByText("mostra"));   // con un seme la tavolozza parte chiusa
    fireEvent.click(screen.getByRole("button", { name: /^Techno/ }));
    expect(onChange2).toHaveBeenLastCalledWith([]);
  });

  it("la tavolozza è aperta a barra vuota e chiusa col primo seme, ma si riapre", () => {
    setup([DEEP]);
    expect(screen.queryByText("In libreria")).toBeNull();
    fireEvent.click(screen.getByText("mostra"));
    expect(screen.getByText("In libreria")).toBeTruthy();
  });

  it("disabilitato: niente campo, niente rimozione", () => {
    setup([DEEP], { disabled: true });
    expect(input().disabled).toBe(true);
    expect((screen.getByLabelText("Togli Deep House") as HTMLButtonElement).disabled).toBe(true);
  });
});
