// Fonte di verità delle chiavi i18n. NIENTE `as const`: i valori devono restare
// `string`/funzioni così `it.ts` può tipizzarsi con `typeof en`.
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
    never: "never",
    empty: "—",
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
    toggleTheme: "Toggle theme",
    themePaper: "Paper",
    themeDark: "Dark",
  },
  settings: {
    languageLabel: "Language",
    languageIt: "Italiano",
    languageEn: "English",
  },
  errors: {} as Record<string, string | ((p: Record<string, unknown>) => string)>,
};

export type Dictionary = typeof en;
