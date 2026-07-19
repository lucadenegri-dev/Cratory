import type { NextConfig } from "next";

// Origin del backend FastAPI, risolto LATO SERVER Next (non NEXT_PUBLIC: il
// browser non lo vede mai). Override con BACKEND_URL solo per setup particolari.
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Next 16 blocca due `next dev` concorrenti sulla stessa distDir (lockfile
  // in <distDir>/dev/lock). La suite E2E (playwright.config.ts) gira sulla
  // porta 3211 in parallelo a un eventuale `next dev` normale su :3000: le
  // serve una distDir separata per non collidere sul lock. NEXT_DIST_DIR è
  // settata solo dal webServer di Playwright.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  async rewrites() {
    return [
      {
        // Proxy verso il backend: il browser chiama /api/* sullo stesso host
        // della pagina (funziona anche da altri dispositivi in LAN) e Next
        // inoltra al backend. Non ci sono route app/api/ da preservare.
        source: "/api/:path*",
        destination: `${BACKEND}/api/:path*`,
      },
    ];
  },
  async redirects() {
    return [
      // La sezione Download e' diventata Wishlist (spec 2026-07-19): i vecchi
      // link/bookmark non si rompono. permanent:false — e' un rename interno.
      { source: "/downloads", destination: "/wishlist", permanent: false },
    ];
  },
};

export default nextConfig;
