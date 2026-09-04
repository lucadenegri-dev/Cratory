import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { IssuesTable } from "@/components/organize/issues-table";
import { groupOrder } from "@/lib/organize/issue-actions";
import type { Issue } from "@/lib/organize/api";

afterEach(cleanup);

// useT() funziona senza provider: il default del context è già "it"
// (stesso pattern di tests/wishlist-row.test.tsx).

vi.mock("@/components/organize/cover-thumb", () => ({
  CoverThumb: () => <span data-testid="thumb" />,
}));

function issue(over: Partial<Issue> & { id: number }): Issue {
  return {
    file_id: 1, location: "library", type: "missing_metadata", field: "genre",
    severity: "warning", detail: "", suggested_fix_json: null, status: "open",
    file_path: `/m/${over.id}.mp3`, artist: `Artist ${over.id}`, title: "T",
    current_value: null, is_new: false,
    ...over,
  };
}

const handlers = () => ({
  onFix: vi.fn(async () => {}), onAccept: vi.fn(async () => {}),
  onDismiss: vi.fn(async () => {}), onReopen: vi.fn(async () => {}),
  onAcceptGroup: vi.fn<(list: Issue[]) => Promise<void>>(async () => {}),
  onDismissGroup: vi.fn<(list: Issue[]) => Promise<void>>(async () => {}),
  onDraft: vi.fn(),
});

function groupHeaders() {
  // Le intestazioni dei gruppi sono i bottoni con aria-expanded.
  return screen.getAllByRole("button", { expanded: true }).map((b) => b.textContent ?? "");
}

describe("IssuesTable: ordine dei gruppi", () => {
  const all = [
    issue({ id: 1, type: "missing_metadata" }),
    issue({ id: 2, type: "missing_metadata" }),
    issue({ id: 3, type: "missing_metadata" }),
    issue({ id: 4, type: "dirty_genre" }),
    issue({ id: 5, type: "dirty_genre" }),
    issue({ id: 6, type: "dirty_genre" }),
  ];

  it("non si scavalcano quando una riga esce dalla lista filtrata", () => {
    const rank = groupOrder(all, "type");
    const h = handlers();
    const { rerender } = render(
      <IssuesTable issues={all} groupBy="type" rank={rank} drafts={{}} {...h} />,
    );
    const before = groupHeaders();
    expect(before).toHaveLength(2);

    // L'utente accetta la 1: con il filtro "aperte" la riga sparisce e il
    // gruppo missing_metadata scende a 2 aperte su 3, sotto le 3 di
    // dirty_genre. Ordinando sulle sole aperte (il bug) i due gruppi si
    // scavalcherebbero; il rango, calcolato sul totale, non cambia → stesso
    // ordine di prima.
    const after = all.map((i) => (i.id === 1 ? { ...i, status: "accepted" as const } : i))
      .filter((i) => i.status === "open");
    rerender(<IssuesTable issues={after} groupBy="type" rank={groupOrder(all, "type")} drafts={{}} {...h} />);
    expect(groupHeaders().map((s) => s.split(/\d/)[0])).toEqual(before.map((s) => s.split(/\d/)[0]));
  });
});

describe("IssuesTable: bozze e azioni di gruppo", () => {
  it("l'input della riga è controllato dalla pagina", () => {
    const h = handlers();
    const list = [issue({ id: 7, field: "genre" })];
    const { rerender } = render(
      <IssuesTable issues={list} groupBy="none" rank={() => 0} drafts={{}} {...h} />,
    );
    const input = screen.getByPlaceholderText("scrivi genre…") as HTMLInputElement;
    expect(input.value).toBe("");
    fireEvent.change(input, { target: { value: "Techno" } });
    expect(h.onDraft).toHaveBeenCalledWith(7, "Techno");
    // il valore mostrato è quello che la pagina ha registrato
    rerender(<IssuesTable issues={list} groupBy="none" rank={() => 0} drafts={{ 7: "Techno" }} {...h} />);
    expect(input.value).toBe("Techno");
  });

  it("senza bozza l'input mostra il suggerimento, anche se arriva dopo il mount", () => {
    const h = handlers();
    const base = issue({ id: 8, field: "artist" });
    const { rerender } = render(
      <IssuesTable issues={[base]} groupBy="none" rank={() => 0} drafts={{}} {...h} />,
    );
    const input = screen.getByPlaceholderText("scrivi artist…") as HTMLInputElement;
    expect(input.value).toBe("");
    const withSug = { ...base, suggested_fix_json: { field: "artist", action: "retag", to: "Aphex Twin" } };
    rerender(<IssuesTable issues={[withSug]} groupBy="none" rank={() => 0} drafts={{}} {...h} />);
    expect(input.value).toBe("Aphex Twin");
  });

  it("accetta/ignora gruppo passano le issue del gruppo, non la chiave", async () => {
    const h = handlers();
    const list = [
      issue({ id: 1, type: "dirty_genre" }),
      issue({ id: 2, type: "dirty_genre" }),
      issue({ id: 3, type: "missing_metadata" }),
    ];
    render(<IssuesTable issues={list} groupBy="type" rank={() => 0} drafts={{}} {...h} />);
    const dirtyHeader = screen.getByText(/genere sporco|dirty genre/i).closest("tr")!;
    const acceptBtn = within(dirtyHeader).getByText("✓ accetta gruppo") as HTMLButtonElement;
    const dismissBtn = within(dirtyHeader).getByText("✕ ignora gruppo") as HTMLButtonElement;
    fireEvent.click(acceptBtn);
    expect(h.onAcceptGroup).toHaveBeenCalledTimes(1);
    expect(h.onAcceptGroup.mock.calls.at(-1)?.[0].map((i) => i.id)).toEqual([1, 2]);
    // finché l'accetta è in volo entrambi i bottoni del gruppo sono disabilitati
    expect(dismissBtn.disabled).toBe(true);
    await waitFor(() => expect(dismissBtn.disabled).toBe(false));
    fireEvent.click(dismissBtn);
    expect(h.onDismissGroup.mock.calls.at(-1)?.[0].map((i) => i.id)).toEqual([1, 2]);
  });
});
