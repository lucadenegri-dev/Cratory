import { test, expect } from "@playwright/test";

// Wishlist (spec 2026-07-19): pagina delle tracce non possedute. Con DB vuoto
// verifichiamo montaggio, tab di stato e redirect dalla vecchia rotta.

test("monta con empty state e tab di stato", async ({ page }) => {
  await page.goto("/wishlist");
  await expect(page.getByRole("heading", { name: "Wishlist" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Tutte/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Mai tentate/ })).toBeVisible();
});

test("/downloads reindirizza a /wishlist", async ({ page }) => {
  await page.goto("/downloads");
  await expect(page).toHaveURL(/\/wishlist$/);
});

// Percorso felice della ricerca Soulseek integrata (Task 6). La e2e avvia il
// backend reale con SLSKD_URL="" (playwright.config.ts): slskd non e'
// configurato, quindi GET /api/downloads/status risponderebbe available:
// false e il bottone "Scarica questo" nel modal resterebbe disabilitato
// (canDownload = available && !running in soulseek-search-modal.tsx). Va
// quindi stubbato anche quell'endpoint, oltre a tracce/ricerca/download: e'
// il provider globale JobsProvider a pollarlo (jobs-provider.tsx), non il
// modal direttamente, quindi lo stub deve essere registrato prima della
// navigazione per intercettare il primo poll.
//
// Nota su baseURL: qui si naviga su "localhost", non sul baseURL di default
// (127.0.0.1, playwright.config.ts). Con 127.0.0.1 il dev server Next blocca
// la websocket di HMR come cross-origin ("allowedDevOrigins") e in questo
// setup (Next 16 + Turbopack) quel fallimento impedisce anche il flush dei
// useEffect della pagina dopo l'hydration: nessun effetto post-mount parte
// piu', quindi il fetch di /api/tracks non arriva mai e la riga della
// traccia non compare (verificato isolando il problema con log temporanei:
// su 127.0.0.1 zero useEffect eseguiti, su localhost partono normalmente).
// Gli altri due test di questo file non lo notano perche' non dipendono da
// side effect post-mount (solo intestazione/tab statici o redirect). Non e'
// un problema del test: e' un limite del dev server su questo host, che
// qui si aggira senza toccare playwright.config.ts (condiviso da tutta la
// suite) ne' next.config.ts.
test("ricerca Soulseek integrata: apri dal menu riga, cerca, scarica", async ({ page }) => {
  const track = {
    id: 1, artist: "Aphex Twin", title: "Xtal", has_local_file: false, archived: false,
    playlists: [], last_download_outcome: null, last_download_reason: null,
    last_download_path: null, album_art_url: null,
  };
  await page.route("**/api/tracks?*", (route) =>
    route.fulfill({ json: { total: 1, items: [track] } }));
  await page.route("**/api/downloads/status", (route) =>
    route.fulfill({ json: {
      available: true, status: "idle", processed: 0, total: 0,
      downloaded: 0, needs_review: 0, not_found: 0, failed: 0,
      playlist_id: null, items: [], error: null, current_label: null,
    } }));
  await page.route("**/api/downloads/review/1", (route) =>
    route.fulfill({ json: { expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 }, downloaded: null, reason: null } }));
  await page.route("**/api/downloads/search", (route) =>
    route.fulfill({ json: { variants: ["Aphex Twin Xtal", "Aphex Twin"], results: [{
      username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac", size: 30000000,
      bitrate: null, length: 294, has_free_slot: true, queue_length: 0,
      upload_speed: null, score: 120, confidence: 0.9, auto_ok: true,
    }] } }));
  const downloadCalls: unknown[] = [];
  await page.route("**/api/downloads/track", async (route) => {
    downloadCalls.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, json: { available: true, status: "running" } });
  });

  await page.goto("http://localhost:3211/wishlist");
  await page.getByLabel("Altre azioni").click();
  await page.getByText("Cerca su Soulseek").click();
  await expect(page.getByText("Xtal.flac")).toBeVisible();
  await page.getByText("Scarica questo").click();
  await expect.poll(() => downloadCalls.length).toBe(1);
  expect(downloadCalls[0]).toMatchObject({ track_id: 1,
    candidate: { username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac" } });
});
