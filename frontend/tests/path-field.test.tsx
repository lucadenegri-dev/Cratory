import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PathField } from "@/components/setup/path-field";

const patchConfigSettings = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  patchConfigSettings: (...a: unknown[]) => patchConfigSettings(...a),
  pickPath: vi.fn(),
}));

describe("PathField", () => {
  afterEach(cleanup);

  it("si riallinea quando il valore normalizzato arriva da fuori (fix 5b)", () => {
    const { rerender } = render(
      <PathField fieldKey="library_root" label="Cartella" value="~/Music" canPick={false} onSaved={() => {}} />,
    );
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("~/Music");

    // Il backend espande "~": senza controllare il campo dal prop, l'input
    // uncontrolled resterebbe fermo su "~/Music" per sempre.
    rerender(
      <PathField fieldKey="library_root" label="Cartella" value="/Users/luca/Music" canPick={false} onSaved={() => {}} />,
    );
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("/Users/luca/Music");
  });

  it("salva sul blur quando il valore è cambiato", async () => {
    patchConfigSettings.mockResolvedValue({});
    render(<PathField fieldKey="ai_model" label="Modello" value="" canPick={false} kind="text" onSaved={() => {}} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "claude-sonnet-4-5" } });
    fireEvent.blur(input);
    expect(patchConfigSettings).toHaveBeenCalledWith({ ai_model: "claude-sonnet-4-5" });
  });
});
