import { expect, test } from "@playwright/test";

// Tutte le impostazioni modificabili sono fixture: il test non tocca mai cartelle o account dell'utente.
test.beforeEach(async ({ page }) => {
  const field = (value: string) => ({ value, source: "env", valid: true, detail: null });
  const secret = { configured: false, source: "env", hint: null };
  let config = {
    library_root: field("/Music/Library"), archive_root: field("/Music/Archive"),
    slskd_download_dir: field("/Music/Downloads"), slskd_url: field("http://localhost:5030"),
    slskd_config_path: field("/config/slskd.yml"), ai_model: field("example-model"),
    share_library: false, download_slots: 3, warning: null,
    spotify_redirect_uri: "http://localhost:8211/api/spotify/callback",
    secrets: Object.fromEntries(["spotify_client_id", "spotify_client_secret", "ai_api_key", "discogs_token", "acoustid_api_key", "slskd_api_key"].map((key) => [key, secret])),
  };
  await page.route("**/api/setup/state", (route) => route.fulfill({ json: { completed: true } }));
  await page.route("**/api/settings/language", (route) => route.fulfill({ json: { language: "it" } }));
  await page.route("**/api/settings/config", async (route) => {
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON();
      config = { ...config, ...Object.fromEntries(Object.entries(patch).map(([key, value]) => [key, field(String(value))])) };
    }
    await route.fulfill({ json: config });
  });
  await page.route("**/api/settings/download-slots", (route) => route.fulfill({ json: { download_slots: route.request().postDataJSON().slots } }));
  await page.route("**/api/files/pick/availability", (route) => route.fulfill({ json: { available: false } }));
  await page.route("**/api/settings/discovery", (route) => route.fulfill({ json: { discogs_enabled: true } }));
  await page.route("**/api/services/status", (route) => route.fulfill({ json: { services: [
    ["spotify", "Spotify"], ["soundcloud", "SoundCloud"], ["slskd", "slskd (Soulseek)"],
    ["discogs", "Discogs"], ["musicbrainz", "MusicBrainz"], ["acoustid", "AcoustID / Chromaprint"], ["anthropic", "Anthropic — AI"],
  ].map(([key, name]) => ({ key, name, configured: ["spotify", "soundcloud", "discogs", "musicbrainz"].includes(key), connected: key === "spotify" ? true : null, optional_ok: null, env: [], optional_env: [], category: "", detail: "", docs: "https://example.com" })) } }));
  await page.route("**/api/slskd/status", (route) => route.fulfill({ json: { configured: false, reachable: false, is_connected: false, is_logged_in: false } }));
  await page.route("**/api/slskd/daemon/status", (route) => route.fulfill({ json: { installed: false, configured: false, reachable: false, owned: null } }));
  await page.route("**/api/soundcloud/status", (route) => route.fulfill({ json: { available: true, username: "example-dj" } }));
});

test("le sezioni conservano le bozze e salvano solo i campi della sezione", async ({ page }) => {
  await page.goto("/settings");
  const nav = page.getByRole("navigation", { name: "Impostazioni" });
  await expect(nav.getByRole("link", { name: "Generali" })).toHaveAttribute("aria-current", "page");
  await nav.getByRole("link", { name: "Libreria", exact: true }).click();
  await page.getByRole("textbox", { name: "Cartella della musica" }).fill("/Music/Draft");
  await nav.getByRole("link", { name: "Download", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Cartella della musica" })).toBeHidden();
  await page.getByRole("textbox", { name: /Cartella dei download/ }).fill("/Downloads/New");
  const patch = page.waitForRequest((r) => r.url().endsWith("/api/settings/config") && r.method() === "PATCH");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  expect((await patch).postDataJSON()).toEqual({ slskd_download_dir: "/Downloads/New" });
  await expect(page.getByText("Salvato ✓", { exact: true }).filter({ visible: true })).toBeVisible();
  await nav.getByRole("link", { name: "Libreria", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /Cartella della musica/ })).toHaveValue("/Music/Draft");
  await nav.getByRole("link", { name: "Collegamenti" }).click();
  await expect(page.getByRole("textbox", { name: "Nome utente SoundCloud" })).toBeHidden();
  await page.getByRole("button", { name: "Gestisci SoundCloud" }).click();
  await page.getByRole("textbox", { name: "Nome utente SoundCloud" }).fill("draft-user");
  await page.getByRole("button", { name: "Gestisci Spotify" }).click();
  await expect(page.getByRole("textbox", { name: "Nome utente SoundCloud" })).toBeHidden();
  await page.getByRole("button", { name: "Gestisci SoundCloud" }).click();
  await expect(page.getByRole("textbox", { name: "Nome utente SoundCloud" })).toHaveValue("draft-user");
});

test("il ritorno da Spotify e i link diretti alle sezioni funzionano su desktop e mobile nei due temi", async ({ page }, testInfo) => {
  await page.goto("/settings?spotify=connected");
  const nav = page.getByRole("navigation", { name: "Impostazioni" });
  await expect(nav.getByRole("link", { name: "Collegamenti" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("✓ Account Spotify collegato.")).toBeVisible();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["dark", "paper"]) {
      await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);
      for (const section of ["Generali", "Libreria", "Download", "Collegamenti", "Backup"]) {
        await nav.getByRole("link", { name: section, exact: true }).click();
        await expect(nav.getByRole("link", { name: section, exact: true })).toHaveAttribute("aria-current", "page");
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      }
    }
  }
  await page.goto("/settings?section=downloads");
  await expect(page.getByRole("spinbutton")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Indirizzo di slskd" })).toBeHidden();
  await page.getByText("Impostazioni avanzate di Soulseek", { exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Indirizzo di slskd" })).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 1000 });
  await nav.getByRole("link", { name: "Collegamenti" }).click();
  await expect(nav.getByRole("link", { name: "Collegamenti" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Spotify", exact: true })).toBeVisible();
  for (const theme of ["dark", "paper"]) {
    await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);
    await expect(page.getByRole("button", { name: "Gestisci Spotify" })).toHaveCSS("color", theme === "dark" ? "rgb(196, 196, 196)" : "rgb(42, 40, 35)");
    await page.screenshot({ path: testInfo.outputPath(`settings-${theme}.png`), fullPage: true, animations: "disabled" });
  }
});
