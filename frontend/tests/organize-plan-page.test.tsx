import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PlanPage from "@/app/organize/plan/page";
import type { ApplyJobState, ApplyResult, Plan } from "@/lib/organize/api";

/* Lo stato del job di apply vive in memoria nel backend e sopravvive al job:
   resta `done` (con il suo esito) fino al prossimo apply. Ricaricando la
   pagina, il primo poll del provider lo riporta come se fosse appena finito.
   La pagina deve reagire solo agli apply che il provider ha visto concludersi
   in QUESTA sessione (`applyDellaSessione`, il loro `started_at`). */

const getPlan = vi.fn();
const buildPlan = vi.fn();

vi.mock("@/lib/organize/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/organize/api")>()),
  getPlan: (...a: unknown[]) => getPlan(...a),
  buildPlan: (...a: unknown[]) => buildPlan(...a),
}));

type Jobs = {
  apply: ApplyJobState;
  applyDellaSessione: string | null;
  startApply: () => Promise<void>;
  refresh: () => void;
};
let jobs: Jobs;
vi.mock("@/components/jobs-provider", () => ({ useJobs: () => jobs }));

const PIANO: Plan = {
  id: 7, status: "draft", created_at: "2026-10-03T15:00:00Z", rules: {},
  ops: [{
    id: 1, seq: 0, kind: "MOVE", file_id: 1, file_path: "/lib/raw_1.mp3",
    before: { path: "/lib/raw_1.mp3" }, after: { path: "/lib/Techno/A/A - Uno.mp3" },
    status: "pending", skipped: false,
  }],
  conflicts: [],
  stats: {
    n_retag: 0, n_cover: 0, n_rename: 0, n_move: 1, n_delete: 0,
    space_freed_bytes: 0, n_conflicts: 0, n_skipped: 0, blocking: false,
  },
};

const IDLE: ApplyJobState = {
  status: "idle", phase: null, processed: 0, total: 0, result: null, error: null,
  started_at: null, finished_at: null,
};

function esito(runId: number): ApplyResult {
  return {
    run_id: runId, applied_ops: 3, skipped_ops: 0, refused: false, stale: false,
    partial: false, failed_op_seq: null, error: null, reason: null,
    started_at: null, finished_at: null,
  };
}

/** Pagina aperta (ricaricata) con il provider ancora a idle e un draft nuovo. */
async function apriConDraft() {
  getPlan.mockResolvedValue(PIANO);
  jobs = { apply: IDLE, applyDellaSessione: null, startApply: vi.fn(async () => {}), refresh: vi.fn() };
  const view = render(<PlanPage />);
  await screen.findByText("raw_1.mp3");
  return view;
}

afterEach(() => {
  cleanup();
});

describe("pagina Plan e stato dell'apply", () => {
  it("ricaricando dopo un apply il draft nuovo resta e l'esito vecchio non compare", async () => {
    const { rerender } = await apriConDraft();

    // Primo poll: l'apply della sessione precedente, ancora `done` in memoria.
    jobs = { ...jobs, apply: { ...IDLE, status: "done", started_at: "A0", result: esito(41) } };
    rerender(<PlanPage />);

    expect(screen.getByText("raw_1.mp3")).toBeTruthy();
    expect(screen.queryByText(/run #41/)).toBeNull();
  });

  it("ne' l'errore di un apply della sessione precedente", async () => {
    const { rerender } = await apriConDraft();

    jobs = { ...jobs, apply: { ...IDLE, status: "error", error: "boom vecchio", started_at: "A0" } };
    rerender(<PlanPage />);

    expect(screen.getByText("raw_1.mp3")).toBeTruthy();
    expect(screen.queryByText(/boom vecchio/)).toBeNull();
  });

  it("ma un apply concluso in questa sessione consuma il draft e ne mostra l'esito", async () => {
    /* Il rovescio: senza, i due test sopra passerebbero anche con una pagina
       che non reagisce mai alla fine di un apply. */
    const { rerender } = await apriConDraft();

    jobs = {
      ...jobs,
      apply: { ...IDLE, status: "done", started_at: "A1", result: esito(42) },
      applyDellaSessione: "A1",
    };
    rerender(<PlanPage />);

    await waitFor(() => expect(screen.queryByText("raw_1.mp3")).toBeNull());
    expect(screen.getByText(/run #42/)).toBeTruthy();
    expect(jobs.refresh).toHaveBeenCalled();
  });
});
