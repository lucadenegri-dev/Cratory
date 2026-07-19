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
