import type { NextConfig } from "next";

// Origin del backend FastAPI, risolto LATO SERVER Next (non NEXT_PUBLIC: il
// browser non lo vede mai). Override con BACKEND_URL solo per setup particolari.
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
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
};

export default nextConfig;
