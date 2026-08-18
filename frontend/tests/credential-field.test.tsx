import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { CredentialField } from "@/components/setup/credential-field";

// Il mock deve esporre OGNI export usato dal componente: vitest solleva
// "No 'errText' export is defined on the mock" al primo accesso mancante.
vi.mock("@/lib/api", async () => ({
  patchConfigSettings: vi.fn().mockResolvedValue({}),
  errText: (e: unknown) => String(e),
}));

const { patchConfigSettings } = await import("@/lib/api");

describe("CredentialField", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("non pre-riempie mai il campo con la chiave configurata", () => {
    render(
      <CredentialField
        fieldKey="ai_api_key"
        label="API key"
        state={{ configured: true, source: "db", hint: "••••a3f9" }}
        onSaved={() => {}}
      />,
    );
    // La chiave configurata si annuncia, ma non finisce dentro l'input.
    expect(screen.getByText(/a3f9/)).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("mostra il campo vuoto quando la chiave non è configurata", () => {
    render(
      <CredentialField
        fieldKey="ai_api_key"
        label="API key"
        state={{ configured: false, source: "env", hint: null }}
        onSaved={() => {}}
      />,
    );
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("");
  });

  it("salva il valore digitato e avvisa il chiamante", async () => {
    const onSaved = vi.fn();
    render(
      <CredentialField
        fieldKey="discogs_token"
        label="Token"
        state={{ configured: false, source: "env", hint: null }}
        onSaved={onSaved}
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "tok-123" } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(patchConfigSettings).toHaveBeenCalledWith({ discogs_token: "tok-123" });
  });
});
