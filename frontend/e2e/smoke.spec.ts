import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";

/**
 * Smoke E2E minimo (E15): ogni rotta principale deve montare senza errori
 * console con un DB vuoto (empty state) e feature esterne disattivate
 * (LIBRARY_ROOT/ARCHIVE_ROOT/SLSKD_URL vuoti via playwright.config.ts).
 *
 * "/downloads/issues" non esiste piu': la pagina e' stata unificata in
 * "/downloads" (vedi docs/superpowers/plans/2026-07-09-download-unificato.md).
 *
 * "/" (dashboard) e' l'unica rotta senza <h1> di PageLayout (nessun `title`
 * passato): per quella verifichiamo solo che <main> renderizzi contenuto.
 */
const ROUTES: { path: string; title: string | null }[] = [
  { path: "/", title: null },
  { path: "/library", title: null },
  { path: "/playlists", title: null },
  { path: "/labels", title: null },
  { path: "/downloads", title: null },
  { path: "/sets", title: null },
  { path: "/transitions", title: null },
  { path: "/analysis", title: null },
  { path: "/discovery", title: "Discovery" },
  { path: "/shazam", title: "Shazam" },
  { path: "/set-builder", title: "Set Builder" },
  { path: "/settings", title: null },
];

// Rumore noto e innocuo che puo' comparire in dev mode: whitelist esplicita,
// tenuta minima e motivata caso per caso (si parte stretti).
const CONSOLE_WHITELIST: RegExp[] = [
  // HMR websocket del dev server: gioco di timing tra chiusura pagina e polling
  // Playwright su networkidle, non un errore applicativo. Non comparirebbe in
  // `next build` + `next start` (produzione).
  /webpack-hmr/,
];

function isWhitelisted(text: string): boolean {
  return CONSOLE_WHITELIST.some((re) => re.test(text));
}

async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (isWhitelisted(text)) return;
    errors.push(text);
  });
  page.on("pageerror", (err) => {
    if (!isWhitelisted(err.message)) errors.push(err.message);
  });
  return errors;
}

for (const { path, title } of ROUTES) {
  test(`${path} renders without console errors`, async ({ page }) => {
    const errors = await collectConsoleErrors(page);

    const response = await page.goto(path);
    expect(response?.ok(), `navigation to ${path} should return a 2xx/3xx response`).toBeTruthy();

    const main = page.locator("main");
    await expect(main).toBeVisible();

    if (title) {
      const h1 = page.locator("main h1", { hasText: title });
      await expect(h1).toBeVisible();
    } else {
      // Nessun titolo atteso (es. dashboard "/"): il contenuto di <main> non
      // deve comunque essere vuoto (empty state incluso).
      await expect(main).not.toBeEmpty();
    }

    // Lascia assestare eventuali effect/fetch asincroni prima di leggere gli errori.
    await page.waitForLoadState("networkidle");

    expect(errors, `console errors on ${path}:\n${errors.join("\n")}`).toEqual([]);
  });
}

// Deep link del dig (E17): "Warp Records" e' un'etichetta reale della libreria
// (verificata via GET /api/labels), non inventata — "Trax Records" del brief
// originale non esiste nella libreria corrente.
//
// Trappola: il <select> del gusto (affinita') e il Combobox del soggetto hanno
// ENTRAMBI ruolo ARIA "combobox" (un <select> nativo lo espone implicitamente).
// Quando ci sono playlist importate il Select renderizza e getByRole("combobox")
// e' ambiguo: il Combobox del soggetto e' pero' sempre il primo in ordine di riga
// (vedi components/discovery-dig-bar.tsx), quindi .first() lo disambigua.
test("deep link per etichetta precompila il soggetto", async ({ page }) => {
  await page.goto("/discovery?seed=label&value=Warp%20Records");
  await expect(page.getByRole("combobox").first()).toHaveValue("Warp Records");
});
