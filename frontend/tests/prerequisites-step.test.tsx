import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PrerequisitesStep } from "@/components/setup/steps/prerequisites";
import type { ProbeComponent } from "@/lib/api";

const getProbe = vi.fn();
const startInstall = vi.fn();
const getInstallStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getProbe: (...a: unknown[]) => getProbe(...a),
  startInstall: (...a: unknown[]) => startInstall(...a),
  getInstallStatus: (...a: unknown[]) => getInstallStatus(...a),
}));

function comp(over: Partial<ProbeComponent>): ProbeComponent {
  return {
    key: "fpcalc", kind: "system", severity: "optional", present: false,
    version: null, source: null, shadowing: null, auto_installable: true, installable: true,
    install_command: null, unlocks: [], docs: "https://esempio.invalid",
    ...over,
  };
}

describe("PrerequisitesStep", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    startInstall.mockResolvedValue({ key: "fpcalc", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "fpcalc", status: "done", log: [], detail: null });
  });
  afterEach(cleanup);

  it("installa in sequenza solo ciò che manca ed è installabile", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "ffmpeg", present: false, installable: false }),
      comp({ key: "fpcalc", present: false, installable: true }),
      comp({ key: "slskd", kind: "daemon", present: true, installable: true }),
    ]});
    render(<PrerequisitesStep onGoToSlskd={() => {}} />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);
    // ffmpeg non ha build su questa piattaforma, slskd c'è già: resta fpcalc.
    await waitFor(() => expect(startInstall).toHaveBeenCalledTimes(1));
    expect(startInstall).toHaveBeenCalledWith("fpcalc");
  });

  it("il bottone è spento quando non c'è niente da installare", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ present: true }),
    ]});
    render(<PrerequisitesStep onGoToSlskd={() => {}} />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    expect((bottone as HTMLButtonElement).disabled).toBe(true);
  });
});
