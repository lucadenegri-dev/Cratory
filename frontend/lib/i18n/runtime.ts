// frontend/lib/i18n/runtime.ts
// Stato lingua accessibile fuori da React (es. lib/api.ts). Il provider in
// index.tsx lo tiene allineato al context. NIENTE import da lib/api.ts qui.
import { en, type Dictionary } from "./en";
import { it } from "./it";

export type Language = "it" | "en";

export const STORAGE_KEY = "cratory-lang";
export const DICTIONARIES: Record<Language, Dictionary> = { it, en };

let currentLanguage: Language = "it";

export function getCurrentLanguage(): Language {
  return currentLanguage;
}

export function setCurrentLanguage(next: Language): void {
  currentLanguage = next;
}

/** Traduce un codice errore API nella lingua attiva; `fallback` se il codice è ignoto. */
export function translateApiError(
  code: string,
  params: Record<string, unknown>,
  fallback: string,
): string {
  const entry = DICTIONARIES[currentLanguage].errors[code];
  if (typeof entry === "string") return entry;
  if (typeof entry === "function") return entry(params);
  return fallback;
}
