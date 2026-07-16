import { describe, expect, it, vi, afterEach } from "vitest";
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Chip, Combobox, SegmentedControl, type ComboOption } from "@/components/ui";

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

describe("Combobox", () => {
  const OPTS: ComboOption[] = [
    { value: "Acid House", label: "Acid House", group: "genere" },
    { value: "Acid Techno", label: "Acid Techno", group: "genere" },
    { value: "Trax Records", label: "Trax Records", group: "etichetta" },
  ];

  // Il Combobox è pienamente controllato: il testo lo detiene il chiamante.
  // L'harness fornisce lo stato React reale che in produzione sta nella pagina,
  // così `fireEvent.change` -> onChange -> setValue -> nuovo `value` in prop.
  // Testare un componente controllato con un onChange inerte proverebbe solo
  // che React fa il suo mestiere.
  function Harness({ onSelect, onChange, options = OPTS, cap }: {
    onSelect?: (o: ComboOption) => void;
    onChange?: (v: string) => void;
    options?: ComboOption[];
    cap?: number;
  }) {
    const [value, setValue] = useState("");
    return (
      <Combobox
        value={value}
        onChange={(v) => { onChange?.(v); setValue(v); }}
        onSelect={onSelect ?? (() => {})}
        options={options}
        cap={cap}
      />
    );
  }

  function setup() {
    const onSelect = vi.fn();
    const onChange = vi.fn();
    render(<Harness onSelect={onSelect} onChange={onChange} />);
    return { onSelect, onChange };
  }

  it("filtra per sottostringa, case-insensitive", () => {
    setup();
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "trax" } });
    expect(screen.getByText("Trax Records")).toBeTruthy();
    expect(screen.queryByText("Acid House")).toBeNull();
  });

  it("mostra generi ed etichette insieme, generi prima", () => {
    setup();
    fireEvent.focus(screen.getByRole("combobox"));
    const labels = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(labels[0]).toContain("Acid House");
    expect(labels[labels.length - 1]).toContain("Trax Records");
  });

  it("Enter sceglie l'opzione evidenziata e riporta il gruppo", () => {
    const { onSelect } = setup();
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ value: "Acid Techno", group: "genere" }));
  });

  it("Escape chiude senza selezionare", () => {
    const { onSelect } = setup();
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("option")).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("accetta testo libero non presente tra i suggerimenti", () => {
    const { onChange } = setup();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Genere Inventato" } });
    expect(onChange).toHaveBeenCalledWith("Genere Inventato");
  });

  it("cappa le voci visibili", () => {
    const many: ComboOption[] = Array.from({ length: 30 }, (_, i) => ({
      value: `g${i}`, label: `g${i}`, group: "genere",
    }));
    render(<Harness options={many} cap={12} />);
    fireEvent.focus(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option").length).toBe(12);
  });
});
