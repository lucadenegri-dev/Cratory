import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DropdownMenu } from "@/components/ui";

afterEach(cleanup);

describe("DropdownMenu", () => {
  it("apre al click e chiude alla selezione", () => {
    const onSelect = vi.fn();
    render(<DropdownMenu label="Compra" items={[{ key: "a", label: "Azione", onSelect }]} />);
    expect(screen.queryByText("Azione")).toBeNull();
    fireEvent.click(screen.getByText("Compra"));
    fireEvent.click(screen.getByText("Azione"));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByText("Azione")).toBeNull();
  });

  it("gli item href sono link in nuova tab", () => {
    render(<DropdownMenu label="Compra" items={[{ key: "b", label: "Bandcamp", href: "https://bandcamp.com/search?q=x" }]} />);
    fireEvent.click(screen.getByText("Compra"));
    const a = screen.getByText("Bandcamp").closest("a");
    expect(a?.getAttribute("href")).toBe("https://bandcamp.com/search?q=x");
    expect(a?.getAttribute("target")).toBe("_blank");
    expect(a?.getAttribute("rel")).toContain("noopener");
  });

  it("chiude con Escape", () => {
    render(<DropdownMenu label="Menu" items={[{ key: "a", label: "Azione", onSelect: () => {} }]} />);
    fireEvent.click(screen.getByText("Menu"));
    expect(screen.getByText("Azione")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("Azione")).toBeNull();
  });

  it("disabled non apre", () => {
    render(<DropdownMenu label="Menu" disabled items={[{ key: "a", label: "Azione", onSelect: () => {} }]} />);
    fireEvent.click(screen.getByText("Menu"));
    expect(screen.queryByText("Azione")).toBeNull();
  });

  it("il click fuori dal menu lo chiude", () => {
    render(<DropdownMenu label="Menu" items={[{ key: "a", label: "Azione", onSelect: () => {} }]} />);
    fireEvent.click(screen.getByText("Menu"));
    expect(screen.getByText("Azione")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("Azione")).toBeNull();
  });

  it("un item href con disabled non e' navigabile", () => {
    const onSelect = vi.fn();
    render(
      <DropdownMenu
        label="Compra"
        items={[{ key: "b", label: "Bandcamp", href: "https://bandcamp.com/search?q=x", disabled: true, onSelect }]}
      />,
    );
    fireEvent.click(screen.getByText("Compra"));
    const a = screen.getByText("Bandcamp").closest("a");
    expect(a?.getAttribute("aria-disabled")).toBe("true");
    expect(a?.className).toContain("pointer-events-none");
    fireEvent.click(a!);
    expect(onSelect).not.toHaveBeenCalled();
    // Il menu resta aperto: l'item disabled non chiude e non naviga.
    expect(screen.getByText("Bandcamp")).toBeTruthy();
  });

  it("ariaLabel diventa il nome accessibile del trigger", () => {
    render(
      <DropdownMenu
        label={<span aria-hidden>•••</span>}
        ariaLabel="Foo"
        items={[{ key: "a", label: "Azione", onSelect: () => {} }]}
      />,
    );
    expect(screen.getByRole("button", { name: "Foo" })).toBeTruthy();
  });
});
