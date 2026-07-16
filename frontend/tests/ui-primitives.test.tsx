import { beforeAll, describe, expect, it, vi, afterEach } from "vitest";
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Chip, Combobox, SegmentedControl, type ComboOption } from "@/components/ui";

afterEach(cleanup);

beforeAll(() => {
  // jsdom non implementa scrollIntoView: senza stub, il Combobox lancerebbe.
  Element.prototype.scrollIntoView = vi.fn();
});

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
  function Harness({ onSelect, onChange, options = OPTS }: {
    onSelect?: (o: ComboOption) => void;
    onChange?: (v: string) => void;
    options?: ComboOption[];
  }) {
    const [value, setValue] = useState("");
    return (
      <Combobox
        value={value}
        onChange={(v) => { onChange?.(v); setValue(v); }}
        onSelect={onSelect ?? (() => {})}
        options={options}
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

  // Riscrittura SEMANTICA di "cappa le voci visibili": il cap era un residuo delle
  // chip (+N altre) e contraddiceva la lista, che gia' scorre (max-h + overflow).
  // Le voci reali sono 319 (66 generi + 228 etichette + 25 stili curati): si vedono
  // tutte, tagliarle a 12 era un blocco, non una protezione.
  it("rende tutte le opzioni, nessun cap", () => {
    const many: ComboOption[] = Array.from({ length: 319 }, (_, i) => ({
      value: `g${i}`, label: `g${i}`, group: "genere",
    }));
    render(<Harness options={many} />);
    fireEvent.focus(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option").length).toBe(319);
  });

  it("ArrowDown porta l'opzione attiva in vista", () => {
    // Obbligatorio insieme alla rimozione del cap: gia' con 12 voci in una box da
    // 256px se ne vedono ~7, con 319 la navigazione da tastiera sarebbe cieca.
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    const many: ComboOption[] = Array.from({ length: 319 }, (_, i) => ({
      value: `g${i}`, label: `g${i}`, group: "genere",
    }));
    render(<Harness options={many} />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(spy).toHaveBeenCalledWith({ block: "nearest" });
    spy.mockRestore();
  });

  it("il mouse NON fa scrollare la lista", () => {
    // onMouseEnter cambia l'opzione attiva, ma l'utente sta gia' guardando quella
    // che tocca: farle saltare la lista sotto il cursore e' peggio del difetto curato.
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    const many: ComboOption[] = Array.from({ length: 319 }, (_, i) => ({
      value: `g${i}`, label: `g${i}`, group: "genere",
    }));
    render(<Harness options={many} />);
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.mouseEnter(screen.getAllByRole("option")[3]);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
