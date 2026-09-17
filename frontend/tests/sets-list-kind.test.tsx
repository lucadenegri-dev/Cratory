import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const listApi = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  apiGet: listApi.apiGet,
}));

import SetsPage from "@/app/sets/page";

afterEach(() => { cleanup(); listApi.apiGet.mockReset(); });

describe("lista dei set", () => {
  it("apre i set manuali sulla pagina manuale e quelli generati sul dettaglio", async () => {
    listApi.apiGet.mockResolvedValue([
      { id: 1, name: "A mano", kind: "manual", strategy: null, target_duration_minutes: null, track_count: 0, total_duration_seconds: 0, generated_by: "manual", created_at: "2026-09-17T10:00:00" },
      { id: 2, name: "Generato", kind: "generated", strategy: "smooth", target_duration_minutes: 60, track_count: 12, total_duration_seconds: 3600, generated_by: "algorithmic", created_at: "2026-09-17T10:00:00" },
    ]);
    render(<SetsPage />);
    const manual = (await screen.findByText("A mano")).closest("a");
    const generated = screen.getByText("Generato").closest("a");
    expect(manual?.getAttribute("href")).toBe("/sets/manual?id=1");
    expect(generated?.getAttribute("href")).toBe("/sets/detail?id=2");
  });
});
