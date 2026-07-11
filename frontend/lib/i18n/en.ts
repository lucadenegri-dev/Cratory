// frontend/lib/i18n/en.ts
// Fonte di verità delle chiavi i18n. NIENTE `as const`: i valori devono
// restare `string`/funzioni così `it.ts` può tipizzarsi con `typeof en`.
export const en = {
  common: {
    loading: "Loading…",
    save: "Save",
    cancel: "Cancel",
    close: "Close",
    confirm: "Confirm",
    delete: "Delete",
    search: "Search",
    all: "All",
    none: "None",
    error: "Error",
    retry: "Retry",
  },
  nav: {
    tagline: "DJ set workbench",
    groupDiscover: "Discover",
    groupCollect: "Collect",
    groupPlay: "Play",
    dashboard: "Dashboard",
    discovery: "Discovery",
    shazam: "Shazam",
    library: "Library",
    playlists: "Playlists",
    labels: "Labels",
    downloads: "Downloads",
    sets: "Sets",
    transitions: "Transitions",
    settings: "Settings",
    index: "Index",
    indexStarting: "Starting…",
    indexStarted: "Started",
    toggleTheme: "Toggle theme",
  },
  settings: {
    languageLabel: "Language",
    languageIt: "Italiano",
    languageEn: "English",
  },
  errors: {} as Record<string, string | ((p: Record<string, unknown>) => string)>,
};

export type Dictionary = typeof en;
