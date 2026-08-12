import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { Settings } from "@/lib/organize/api";

const getSettings = vi.fn<() => Promise<Settings>>();
const updateSettings = vi.fn();
const listProviders = vi.fn(async () => []);
const runFingerprint = vi.fn();

vi.mock("@/lib/organize/api", () => ({
  getSettings: (...a: unknown[]) => getSettings(...(a as [])),
  updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
  listProviders: (...a: unknown[]) => listProviders(...(a as [])),
  runFingerprint: (...a: unknown[]) => runFingerprint(...(a as [])),
}));

const { OrganizeSection } = await import("@/components/settings/organize-section");

const settings: Settings = {
  naming_template: "{artist} - {title}",
  folder_template: "{genre}/{artist}",
} as Settings;

beforeEach(() => {
  getSettings.mockResolvedValue(settings);
  updateSettings.mockResolvedValue(settings);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Impostazioni unica", () => {
  it("la pagina Impostazioni di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../app/organize/settings/page.tsx"))).toBe(false);
  });

  it("la sezione Organize è montata nella pagina unica, sotto la sua intestazione", () => {
    const page = readFileSync(resolve(__dirname, "../app/settings/page.tsx"), "utf8");
    expect(page).toContain("<OrganizeSection />");
    expect(page).toMatch(/groupOrganize[\s\S]{0,120}<OrganizeSection \/>/);
  });

  it("carica i template e li mostra", async () => {
    render(<OrganizeSection />);
    await waitFor(() => expect(screen.getByDisplayValue("{artist} - {title}")).toBeTruthy());
    expect(screen.getByDisplayValue("{genre}/{artist}")).toBeTruthy();
  });

  it("salva i template modificati", async () => {
    /* Non basta che la sezione si veda: deve ancora SALVARE. È l'unico
       comportamento che la pagina assorbita forniva davvero. */
    render(<OrganizeSection />);
    await waitFor(() => expect(screen.getByDisplayValue("{artist} - {title}")).toBeTruthy());

    const input = screen.getByDisplayValue("{artist} - {title}");
    fireEvent.change(input, { target: { value: "{artist} — {title}" } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));

    await waitFor(() => expect(updateSettings).toHaveBeenCalledTimes(1));
    expect(updateSettings.mock.calls[0][0]).toMatchObject({ folder_template: "{genre}/{artist}" });
  });
});
