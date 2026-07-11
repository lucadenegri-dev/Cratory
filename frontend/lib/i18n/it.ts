// frontend/lib/i18n/it.ts
// Traduzione italiana: `Dictionary` (= typeof en) garantisce a compile-time
// che ogni chiave esista e nessuna sia di troppo.
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
    inProgress: "In corso",
  },
  nav: {
    tagline: "Workbench per DJ set",
    groupDiscover: "Scopri",
    groupCollect: "Colleziona",
    groupPlay: "Suona",
    dashboard: "Dashboard",
    discovery: "Discovery",
    shazam: "Shazam",
    library: "Libreria",
    playlists: "Playlists",
    labels: "Etichette",
    downloads: "Download",
    sets: "Set",
    transitions: "Transizioni",
    settings: "Impostazioni",
    index: "Indicizza",
    indexStarting: "Avvio…",
    indexStarted: "Avviata",
    toggleTheme: "Cambia tema",
  },
  settings: {
    languageLabel: "Lingua",
    languageIt: "Italiano",
    languageEn: "English",
  },
  jobs: {
    shazamIdentify: "Identificazione mix",
    soulseekDownload: "Download Soulseek",
    libraryIndex: "Indicizzazione libreria",
    completed: "Completata",
    downloadSummary: (downloaded: number, pending: number) =>
      `${downloaded} scaricate${pending > 0 ? ` · ${pending} da sistemare` : ""}`,
    moreJobs: (n: number) => (n === 1 ? "+1 altro job" : `+${n} altri job`),
  },
  errors: {},
};
