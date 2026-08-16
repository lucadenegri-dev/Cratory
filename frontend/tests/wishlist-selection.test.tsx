import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SelectionBar } from "@/components/wishlist-selection-bar";

afterEach(cleanup);

describe("SelectionBar", () => {
  it("resta invisibile senza selezione", () => {
    const { container } = render(
      <SelectionBar count={0} onEnqueue={vi.fn()} onClear={vi.fn()} busy={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("mostra il conteggio e accoda", () => {
    const onEnqueue = vi.fn();
    render(<SelectionBar count={12} onEnqueue={onEnqueue} onClear={vi.fn()} busy={false} />);
    expect(screen.getByText("Accoda 12 tracce")).toBeTruthy();
    screen.getByText("Accoda 12 tracce").click();
    expect(onEnqueue).toHaveBeenCalled();
  });
});
