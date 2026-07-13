import { defineConfig } from "@playwright/test";

// Suite E2E smoke: porte dedicate (8211/3211) diverse da quelle di sviluppo
// (8000/3000), cosi' non collide mai con i server di dev gia' in esecuzione.
// DB di test isolato sotto backend/data/ (gia' in .gitignore) e feature a
// integrazione esterna disattivate (root/URL vuoti) per un avvio pulito e
// deterministico.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3211",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
  webServer: [
    {
      command: ".venv/bin/python -m uvicorn app.main:app --port 8211",
      cwd: "../backend",
      url: "http://127.0.0.1:8211/docs",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DATABASE_URL: "sqlite:///./data/test_e2e.db",
        LIBRARY_ROOT: "",
        ARCHIVE_ROOT: "",
        SLSKD_URL: "",
      },
    },
    {
      command: "npm run dev -- -p 3211",
      cwd: ".",
      url: "http://127.0.0.1:3211",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        BACKEND_URL: "http://127.0.0.1:8211",
        // distDir dedicata: evita di collidere col lockfile di un `next dev`
        // normale già in esecuzione su :3000 (Next 16, vedi next.config.ts).
        NEXT_DIST_DIR: ".next-e2e",
      },
    },
  ],
});
