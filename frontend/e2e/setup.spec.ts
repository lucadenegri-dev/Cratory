import { expect, test } from "@playwright/test";

/* Il wizard raggiunto direttamente: i cinque passi si attraversano e l'uscita
   riporta in dashboard (slskd non ha più un passo suo: la sua riga nei
   prerequisiti chiede le credenziali e installa da sola). Il redirect
   automatico del primo avvio è coperto dal test unitario di SetupGate: qui
   il flag è già a "completato" per non far dirottare tutta la suite. */
test("il wizard si attraversa e si esce", async ({ page }) => {
  await page.goto("/setup");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  for (let i = 0; i < 4; i++) {
    // Ancorato: senza gli estremi la regex intercetta anche il pulsante
    // "Open Next.js Dev Tools" del dev server (il suo nome accessibile
    // contiene "Next"), che in `npm run dev` sta sempre in pagina.
    await page.getByRole("button", { name: /^(avanti|next)$/i }).click();
  }
  await page.getByRole("button", { name: /entra nell'app|enter the app/i }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("si può saltare del tutto", async ({ page }) => {
  await page.goto("/setup");
  await page.getByRole("button", { name: /salta la configurazione|skip setup/i }).click();
  await expect(page).toHaveURL(/\/$/);
});
