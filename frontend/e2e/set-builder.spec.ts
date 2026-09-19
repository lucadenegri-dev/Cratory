import { test, expect } from "@playwright/test";

// Percorso del set manuale (spec 2026-09-15, tappe 1-2) contro il backend reale
// avviato dalla configurazione Playwright con DB vuoto. Niente playlist né
// tracce, quindi il set nasce senza origine e il materiale arriva dalla ricerca
// in libreria: le tracce le creiamo via API prima di aprire la pagina.

/** Crea `n` tracce possedute e ritorna i loro id, nell'ordine. */
async function seminaTracce(request: import("@playwright/test").APIRequestContext, n: number) {
  const righe = Array.from({ length: n }, (_, i) => `Artista ${i} - Traccia ${i}`).join("\n");
  const res = await request.post("/api/playlists/import-manual", {
    data: { name: `E2E ${Date.now()}`, text: righe },
  });
  expect(res.ok()).toBeTruthy();
  // L'import manuale risponde con un report (`playlist_id`), non con la playlist.
  const report = await res.json();
  const tracce = await (await request.get(`/api/playlists/${report.playlist_id}/tracks`)).json();
  return { playlistId: report.playlist_id as number, trackIds: tracce.map((t: { id: number }) => t.id) };
}

test("alternative e riserva sopravvivono al ricaricamento", async ({ page, request }) => {
  const { playlistId, trackIds } = await seminaTracce(request, 4);

  // Set dalla playlist appena creata, con due tracce già nel percorso: la pagina
  // parte da uno stato utile invece che vuoto.
  const creato = await request.post("/api/sets/manual", { data: { playlist_id: playlistId } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, {
    data: { expected_revision: 0, track_ids: [trackIds[0], trackIds[1]] },
  });

  await page.goto(`/sets/manual?id=${set.id}`);
  // Nel percorso: la stessa traccia compare anche fra il materiale, che elenca
  // pure quelle già nel set.
  await expect(page.getByTestId("path-panel").getByText("Traccia 0")).toBeVisible();

  // Seleziona la prima riga del percorso, poi tieni la terza traccia come sua
  // candidata: il comando compare sulle righe del materiale solo con una riga
  // selezionata, perché senza non avrebbe un punto a cui attaccarla.
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 0/ }).click();
  const rigaMateriale = page.getByTestId("material-panel").locator("li")
    .filter({ hasText: "Traccia 2" });
  await rigaMateriale.getByTitle("Tieni come alternativa").click();
  await expect(page.getByTestId("detail-panel").getByText("Traccia 2")).toBeVisible();

  // Sceglila: diventa attiva e la precedente resta fra le candidate.
  await page.getByTestId("detail-panel").getByRole("button", { name: "Usa" }).click();
  await expect(page.getByTestId("path-panel").getByText("Traccia 2")).toBeVisible();
  await expect(page.getByTestId("detail-panel").getByText("Traccia 0")).toBeVisible();

  // Metti da parte la quarta traccia.
  await page.getByTestId("material-panel").locator("li").filter({ hasText: "Traccia 3" })
    .getByTitle("Metti da parte per la serata").click();
  await expect(page.getByTestId("reserve-panel").getByText("Traccia 3")).toBeVisible();

  // Ricarica: percorso, candidate e riserva sono ancora lì.
  await page.reload();
  await expect(page.getByTestId("path-panel").getByText("Traccia 2")).toBeVisible();
  await expect(page.getByTestId("reserve-panel").getByText("Traccia 3")).toBeVisible();
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 2/ }).click();
  await expect(page.getByTestId("detail-panel").getByText("Traccia 0")).toBeVisible();
});

test("sequenze, banco e annulla sopravvivono al ricaricamento", async ({ page, request }) => {
  const { playlistId, trackIds } = await seminaTracce(request, 4);
  const creato = await request.post("/api/sets/manual", { data: { playlist_id: playlistId } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, {
    data: { expected_revision: 0, track_ids: trackIds },
  });

  await page.goto(`/sets/manual?id=${set.id}`);
  const percorso = page.getByTestId("path-panel");
  await expect(percorso.getByText("Traccia 0")).toBeVisible();

  // Raggruppa le due centrali: il percorso resta di quattro righe, cambia solo
  // come e' diviso.
  const riga = (n: number) => percorso.locator("li").filter({ hasText: `Traccia ${n}` });
  await riga(1).getByLabel("Seleziona la riga").check();
  await riga(2).getByLabel("Seleziona la riga").check();
  await page.getByRole("button", { name: "Raggruppa" }).click();
  await expect(percorso.locator("li")).toHaveCount(4);
  await expect(percorso.locator("section")).toHaveCount(3);

  // Parcheggia la sequenza centrale sul banco: due righe restano nel percorso.
  await percorso.locator("section").nth(1).getByTitle("Sposta sul banco").click();
  await expect(page.getByTestId("bench-panel").getByText("Traccia 1")).toBeVisible();
  await expect(percorso.locator("li")).toHaveCount(2);

  // Due annulla riportano il percorso a quattro righe in una sequenza sola.
  await page.getByRole("button", { name: "Annulla" }).click();
  await expect(percorso.locator("li")).toHaveCount(4);
  await page.getByRole("button", { name: "Annulla" }).click();
  await expect(percorso.locator("section")).toHaveCount(1);

  // Lo stato annullato e' quello salvato, non una finzione della pagina.
  await page.reload();
  await expect(page.getByTestId("path-panel").locator("li")).toHaveCount(4);
  await expect(page.getByTestId("path-panel").locator("section")).toHaveCount(1);
});
