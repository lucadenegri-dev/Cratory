import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { SummaryStep } from "@/components/setup/steps/summary";
import type { ProbeComponent, ServiceStatus } from "@/lib/api";

// Il mock deve esporre OGNI export usato dal componente: vitest solleva
// "No 'X' export is defined on the mock" al primo accesso mancante (stesso
// pattern di tests/credential-field.test.tsx).
const getProbe = vi.fn();
const servicesStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  getProbe: (...a: unknown[]) => getProbe(...a),
  servicesStatus: (...a: unknown[]) => servicesStatus(...a),
}));

function comp(over: Partial<ProbeComponent>): ProbeComponent {
  return {
    key: "ffmpeg", kind: "system", severity: "required", present: true,
    version: "6.0", source: "path", shadowing: null, auto_installable: true,
    installable: true, install_method: "download", install_command: null, unlocks: [], docs: "https://esempio.invalid",
    ...over,
  };
}

function svc(over: Partial<ServiceStatus>): ServiceStatus {
  return {
    key: "spotify", name: "Spotify", category: "Streaming", configured: true,
    connected: null, detail: "", env: [], optional_env: [], optional_ok: null,
    docs: "https://esempio.invalid",
    ...over,
  };
}

describe("SummaryStep", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  /* Qui stavano due test su slskd: "compare una sola volta, non due" e "la
     riga fusa usa lo stato del probe, non quello del servizio". Descrivevano
     un mondo in cui slskd era insieme componente e servizio, e la de-duplica
     serviva a non mostrarlo due volte. Non e' piu' rappresentabile: slskd e'
     uscito dal probe (vedi backend/tests/test_system_probe.py, che sorveglia
     l'elenco dei componenti), quindi un componente non puo' piu' coincidere
     con un servizio. */

  it("componenti e servizi restano righe distinte", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "ffmpeg", present: true }),
    ]});
    servicesStatus.mockResolvedValue({ services: [
      svc({ key: "spotify", name: "Spotify", configured: true }),
    ]});
    render(<SummaryStep />);

    await waitFor(() => expect(screen.getByText("ffmpeg")).toBeTruthy());
    expect(screen.getByText("Spotify")).toBeTruthy();
  });
});
