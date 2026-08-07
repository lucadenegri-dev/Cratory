import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigCard } from "@/components/settings/config-card";
import type { ConfigSettings, FieldState } from "@/lib/api";

const getConfigSettings = vi.fn();
const patchConfigSettings = vi.fn();
const pickerAvailability = vi.fn();
const pickPath = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  getConfigSettings: (...a: unknown[]) => getConfigSettings(...a),
  patchConfigSettings: (...a: unknown[]) => patchConfigSettings(...a),
  setLibraryShare: vi.fn(),
  pickerAvailability: (...a: unknown[]) => pickerAvailability(...a),
  pickPath: (...a: unknown[]) => pickPath(...a),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const field = (value: string): FieldState =>
  ({ value, source: "env", valid: true, detail: null });

const CONFIG: ConfigSettings = {
  library_root: field("/Users/x/Music"),
  archive_root: field(""),
  slskd_download_dir: field("/Users/x/Downloads"),
  slskd_url: field("http://localhost:5030"),
  slskd_config_path: field(""),
  share_library: false,
  warning: null,
};

async function mount(available: boolean) {
  getConfigSettings.mockResolvedValue(CONFIG);
  pickerAvailability.mockResolvedValue({ available });
  await act(async () => {
    render(<ConfigCard />);
  });
}

describe("ConfigCard + picker", () => {
  it("con picker disponibile mostra Sfoglia sui 4 campi percorso", async () => {
    await mount(true);
    expect(screen.getAllByRole("button", { name: "Sfoglia…" })).toHaveLength(4);
  });

  it("senza picker nessun pulsante Sfoglia (resta l'input testuale)", async () => {
    await mount(false);
    expect(screen.queryByRole("button", { name: "Sfoglia…" })).toBeNull();
    expect(screen.getByDisplayValue("/Users/x/Music")).toBeTruthy();
  });

  it("il percorso scelto riempie la bozza senza salvare", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: "/Volumes/Dischi/Musica" });
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByDisplayValue("/Volumes/Dischi/Musica")).toBeTruthy();
    expect(patchConfigSettings).not.toHaveBeenCalled();
  });

  it("annullo del dialog: la bozza non cambia", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: null });
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByDisplayValue("/Users/x/Music")).toBeTruthy();
  });

  it("errore del picker mostrato nel banner della card", async () => {
    await mount(true);
    pickPath.mockRejectedValue(new Error("Un dialog di scelta è già aperto sulla macchina del backend."));
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByText(/già aperto/)).toBeTruthy();
  });
});
