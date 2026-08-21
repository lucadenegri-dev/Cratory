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

  it("slskd compare una sola volta, non due", async () => {
    // Prima del fix: una riga "slskd" (dal probe, kind daemon) e una riga
    // "slskd (Soulseek)" (dai servizi) — stessa cosa, due nomi, due stati
    // potenzialmente diversi.
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "slskd", kind: "daemon", present: true }),
    ]});
    servicesStatus.mockResolvedValue({ services: [
      svc({ key: "slskd", name: "slskd (Soulseek)", configured: false }),
    ]});
    render(<SummaryStep />);

    await waitFor(() => expect(screen.getByText("slskd (Soulseek)")).toBeTruthy());
    expect(screen.queryByText("slskd")).toBeNull();
    expect(screen.getAllByText(/slskd/i)).toHaveLength(1);
  });

  it("la riga fusa usa lo stato del probe (present), non quello del servizio (configured)", async () => {
    // Il caso che il fix 3 del probe esiste per riconoscere: demone già
    // acceso ma non ancora configurato. `present` è vero, `configured` è
    // falso — la riga deve dire "acceso": è quello che sta succedendo
    // davvero, non "configured" che direbbe lo sbagliato "spento".
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "slskd", kind: "daemon", present: true }),
    ]});
    servicesStatus.mockResolvedValue({ services: [
      svc({ key: "slskd", name: "slskd (Soulseek)", configured: false }),
    ]});
    render(<SummaryStep />);

    const riga = await screen.findByText("slskd (Soulseek)");
    const stato = riga.parentElement?.textContent ?? "";
    expect(stato).toMatch(/acceso|on/i);
  });

  it("componenti e servizi non-demone restano righe distinte", async () => {
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
