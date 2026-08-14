import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    // Fuso fisso: alcuni test asserisci risultati di Date/Intl (es.
    // tests/format.test.ts) su timestamp UTC letterali. Senza un fuso fisso
    // un runner a UTC+12 o oltre (es. Auckland) puo' far cadere quei
    // timestamp sul giorno successivo in locale e rompere le stringhe attese.
    // Europe/Rome riflette anche l'utenza reale dell'app (self-hosted,
    // singolo utente italiano).
    env: { TZ: "Europe/Rome" },
  },
  resolve: {
    alias: {
      "@": __dirname,
    },
  },
});
