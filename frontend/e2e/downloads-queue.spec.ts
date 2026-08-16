import { test, expect } from "@playwright/test";

// La coda con API stubbate: il test non dipende da slskd né dal DB.
test("la pagina /downloads mostra intestazione, slot occupati ed etichette per item in corso e in attesa", async ({ page }) => {
  await page.route("**/api/downloads/queue", (route) =>
    route.fulfill({ json: { slots: 3, active: 1,
      pause: { paused: false, reason: null, retry_in_seconds: null }, items: [
      { id: 1, track_id: 10, label: "Aphex Twin — Xtal", kind: "soulseek_auto",
        state: "running", outcome: null, phase: "downloading", bytes_done: 50,
        bytes_total: 100, attempts: 1, error: null, position: 0 },
      { id: 2, track_id: 11, label: "Boards of Canada — Roygbiv", kind: "soulseek_auto",
        state: "queued", outcome: null, phase: null, bytes_done: null,
        bytes_total: null, attempts: 0, error: null, position: 1 },
    ] } }));

  await page.goto("/downloads");
  await expect(page.getByRole("heading", { name: "Download" })).toBeVisible();
  await expect(page.getByText("1 di 3 in corso")).toBeVisible();
  await expect(page.getByText("Aphex Twin — Xtal")).toBeVisible();
  await expect(page.getByText("Boards of Canada — Roygbiv")).toBeVisible();
});

// La coda in pausa: la pagina deve dirlo in testa, altrimenti gli item «in
// attesa» restano fermi senza spiegazione.
test("la pagina /downloads spiega perché la coda è ferma", async ({ page }) => {
  await page.route("**/api/downloads/queue", (route) =>
    route.fulfill({ json: { slots: 3, active: 0,
      pause: { paused: true, reason: "unreachable", retry_in_seconds: 42 }, items: [
      { id: 1, track_id: 10, label: "Aphex Twin — Xtal", kind: "soulseek_auto",
        state: "queued", outcome: null, phase: null, bytes_done: null,
        bytes_total: null, attempts: 0, error: null, position: 0 },
    ] } }));

  await page.goto("/downloads");
  await expect(page.getByText("Coda in pausa")).toBeVisible();
  await expect(page.getByText(/Riprovo fra 42 secondi/)).toBeVisible();
});
