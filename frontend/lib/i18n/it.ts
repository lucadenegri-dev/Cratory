// Traduzione italiana: `Dictionary` (= typeof en) garantisce a compile-time che
// ogni chiave esista e nessuna sia di troppo.
import type { Dictionary } from "./en";

export const it: Dictionary = {
  common: {
    loading: "Caricamento…",
    save: "Salva",
    cancel: "Annulla",
    close: "Chiudi",
    confirm: "Conferma",
    delete: "Elimina",
    search: "Cerca",
    all: "Tutte",
    none: "Nessuna",
    error: "Errore",
    retry: "Riprova",
    never: "mai",
    empty: "—",
    guide: "Guida",
    inProgress: "In corso",
  },
  jobs: {
    scan: "Scansione",
    apply: "Applicazione",
    providerLookup: "Ricerca provider",
  },
  nav: {
    tagline: "file → rekordbox",
    sources: "Sources",
    files: "Files",
    issues: "Issues",
    duplicates: "Duplicates",
    plan: "Plan",
    history: "History",
    settings: "Settings",
    toggleTheme: "Cambia tema",
    themePaper: "Paper",
    themeDark: "Dark",
  },
  settings: {
    languageLabel: "Lingua",
    languageIt: "Italiano",
    languageEn: "English",
  },
  errors: {},
};
