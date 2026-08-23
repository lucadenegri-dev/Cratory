"use client";

/* L'unico posto che parla col guscio desktop per gli aggiornamenti.
 *
 * Import dinamici come in lib/external-url.ts: nel build per il browser il
 * codice di Tauri non entra nel bundle iniziale e senza guscio non viene
 * nemmeno scaricato. E' un modulo separato anche per una ragione di prova: i
 * test del provider lo sostituiscono in blocco, invece di simulare l'intera
 * API di Tauri. */

export type InfoAggiornamento = { versione: string; note: string | null; data: string | null };
export type ErroreAggiornamento = { codice: string; dettaglio: string };
export type Progresso = { scaricati: number; totale: number | null };

export async function controlla(): Promise<InfoAggiornamento | null> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<InfoAggiornamento | null>("controlla_aggiornamento");
}

export async function installa(): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("installa_aggiornamento");
}

export async function riavvia(): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("riavvia_app");
}

/** Entrambe restituiscono la funzione per smettere di ascoltare. */
export async function ascoltaProgresso(su: (p: Progresso) => void): Promise<() => void> {
  const { listen } = await import("@tauri-apps/api/event");
  return listen<Progresso>("aggiornamento://progresso", (e) => su(e.payload));
}

export async function ascoltaInstallazione(su: () => void): Promise<() => void> {
  const { listen } = await import("@tauri-apps/api/event");
  return listen("aggiornamento://installazione", () => su());
}

/** Un comando Rust che ritorna `Err` rifiuta la promise con l'oggetto
 *  serializzato. Se arriva qualcos'altro — un errore di trasporto, il guscio
 *  che non risponde — non lo si spaccia per un codice che non c'era. */
export function erroreDi(e: unknown): ErroreAggiornamento {
  if (e && typeof e === "object" && "codice" in e && "dettaglio" in e) {
    return e as ErroreAggiornamento;
  }
  return { codice: "sconosciuto", dettaglio: String(e) };
}
