import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Chip, SegmentedControl } from "@/components/ui";

afterEach(cleanup);

describe("SegmentedControl", () => {
  const opts = [
    { value: "a" as const, label: "Alpha" },
    { value: "b" as const, label: "Beta" },
  ];

  it("marca l'opzione attiva con aria-pressed", () => {
    render(<SegmentedControl value="a" onChange={() => {}} options={opts} />);
    expect(screen.getByText("Alpha").closest("button")?.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Beta").closest("button")?.getAttribute("aria-pressed")).toBe("false");
  });

  it("notifica il valore scelto", () => {
    const onChange = vi.fn();
    render(<SegmentedControl value="a" onChange={onChange} options={opts} />);
    fireEvent.click(screen.getByText("Beta"));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("disabled blocca il cambio", () => {
    const onChange = vi.fn();
    render(<SegmentedControl value="a" onChange={onChange} options={opts} disabled />);
    fireEvent.click(screen.getByText("Beta"));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Chip", () => {
  it("riflette lo stato attivo", () => {
    render(<Chip on onClick={() => {}}>Acid House</Chip>);
    expect(screen.getByText("Acid House").getAttribute("aria-pressed")).toBe("true");
  });
});
