import { translateApiError } from "@/lib/i18n/runtime";

// Base API vuota = stesso host della pagina: le chiamate /api/* passano dal
// rewrite di next.config.ts verso il backend, quindi l'app funziona anche
// aperta da un altro dispositivo in LAN. NEXT_PUBLIC_API_URL resta come
// override opzionale solo per setup particolari (backend su origin diverso).
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export const SPOTIFY_LOGIN_URL = `${API}/api/spotify/login`;

/** Errore di una chiamata API: messaggio già tradotto (via translateApiError)
 *  più status HTTP e code opzionale, per i call site che vogliono distinguerli. */
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Estrae un messaggio leggibile da un errore catturato in un `catch (e)`. */
export function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    let code: string | undefined;
    try {
      const body = await res.json();
      const d = body.detail;
      if (d && typeof d === "object" && !Array.isArray(d) && typeof d.code === "string") {
        detail = translateApiError(d.code, d.params ?? {}, d.message ?? res.statusText);
        code = d.code;
      } else if (typeof d === "string") {
        detail = d;
      } else if (d != null) {
        // Body d'errore JSON senza `detail` stringa: non perdere il fallback
        // statusText (JSON.stringify(undefined) === undefined lo azzererebbe).
        detail = JSON.stringify(d);
      }
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
  opts?: { signal?: AbortSignal },
): Promise<T> {
  // Niente `new URL(...)`: con base relativa (API vuota) lancerebbe. La query
  // string viene costruita a mano, così l'URL resta relativo allo stesso host.
  let url = API + path;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  return handle<T>(await fetch(url, { signal: opts?.signal }));
}

export async function apiPost<T>(path: string, body?: unknown, opts?: { signal?: AbortSignal }): Promise<T> {
  return apiSend<T>("POST", path, body, opts);
}

export async function apiPatch<T>(path: string, body?: unknown, opts?: { signal?: AbortSignal }): Promise<T> {
  return apiSend<T>("PATCH", path, body, opts);
}

export async function apiPut<T>(path: string, body?: unknown, opts?: { signal?: AbortSignal }): Promise<T> {
  return apiSend<T>("PUT", path, body ?? {}, opts);
}

export async function apiDelete<T>(path: string, opts?: { signal?: AbortSignal }): Promise<T> {
  return apiSend<T>("DELETE", path, undefined, opts);
}

async function apiSend<T>(method: string, path: string, body?: unknown, opts?: { signal?: AbortSignal }): Promise<T> {
  return handle<T>(
    await fetch(API + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts?.signal,
    }),
  );
}

/** Upload multipart: niente header Content-Type manuale, lo imposta fetch col boundary. */
export async function apiUpload<T>(path: string, body: FormData): Promise<T> {
  return handle<T>(await fetch(API + path, { method: "POST", body }));
}
