import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ServiceCard } from "@/components/setup/service-card";

// Il mock deve esporre OGNI export usato dal componente e dai suoi figli
// (CredentialField, ServiceGuide): stesso pattern di tests/credential-field.test.tsx.
const testCredential = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  testCredential: (...a: unknown[]) => testCredential(...a),
  patchConfigSettings: vi.fn().mockResolvedValue({}),
}));

describe("ServiceCard", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("key_accepted (AcoustID) non si legge come un fallimento (fix 3)", async () => {
    testCredential.mockResolvedValue({ ok: true, code: "key_accepted", detail: "invalid fingerprint" });
    render(
      <ServiceCard
        service="acoustid"
        secrets={{
          spotify_client_id: { configured: false, source: "env", hint: null },
          spotify_client_secret: { configured: false, source: "env", hint: null },
          ai_api_key: { configured: false, source: "env", hint: null },
          discogs_token: { configured: false, source: "env", hint: null },
          acoustid_api_key: { configured: true, source: "db", hint: "••••a3f9" },
          slskd_api_key: { configured: false, source: "env", hint: null },
        }}
        docsUrl="https://acoustid.org"
        onSaved={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /prova|test/i }));

    // Deve avere un testo dedicato, non "Funziona — invalid fingerprint"
    // (il ramo generico di successo appenderebbe il dettaglio grezzo del
    // provider, che qui è proprio la prova che la chiave è stata accettata).
    await waitFor(() => expect(screen.getByText(/accettato|accepted/i)).toBeTruthy());
    expect(screen.queryByText(/invalid fingerprint/)).toBeNull();
  });
});
