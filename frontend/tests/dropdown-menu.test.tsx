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
});
