import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Popover } from "@/components/ui";

afterEach(cleanup);

describe("Popover", () => {
  it("apre sul trigger", () => {
    render(<Popover trigger={<span>apri</span>}><p>contenuto</p></Popover>);
    expect(screen.queryByText("contenuto")).toBeNull();
    fireEvent.click(screen.getByText("apri"));
    expect(screen.getByText("contenuto")).toBeTruthy();
  });

  it("chiude su Escape", () => {
    render(<Popover trigger={<span>apri</span>}><p>contenuto</p></Popover>);
    fireEvent.click(screen.getByText("apri"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("contenuto")).toBeNull();
  });

  it("chiude su click esterno", () => {
    render(
      <div>
        <Popover trigger={<span>apri</span>}><p>contenuto</p></Popover>
        <button>fuori</button>
      </div>,
    );
    fireEvent.click(screen.getByText("apri"));
    fireEvent.mouseDown(screen.getByText("fuori"));
    expect(screen.queryByText("contenuto")).toBeNull();
  });

  it("notifica il cambio di stato", () => {
    const onOpenChange = vi.fn();
    render(<Popover trigger={<span>apri</span>} onOpenChange={onOpenChange}><p>c</p></Popover>);
    fireEvent.click(screen.getByText("apri"));
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });
});
