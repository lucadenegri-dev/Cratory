// frontend/lib/i18n/index.tsx
"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiGet, apiPut } from "@/lib/api";
import { type Dictionary } from "./en";
import { it } from "./it";
import { DICTIONARIES, STORAGE_KEY, setCurrentLanguage, type Language } from "./runtime";

export type { Dictionary, Language };
export { getCurrentLanguage, translateApiError } from "./runtime";

const I18nContext = createContext<{
  lang: Language;
  t: Dictionary;
  setLang: (next: Language) => void;
}>({ lang: "it", t: it, setLang: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>("it");

  useEffect(() => {
    /* localStorage evita il flash; il backend resta la fonte persistente. */
    const stored = localStorage.getItem(STORAGE_KEY);
    const initial: Language = stored === "en" ? "en" : "it";
    setCurrentLanguage(initial);
    document.documentElement.lang = initial;
    // requestAnimationFrame: evita setState sincrono nel body dell'effect
    // (stesso pattern di components/theme-toggle.tsx per react-hooks/set-state-in-effect).
    const raf = requestAnimationFrame(() => setLangState(initial));
    apiGet<{ language: Language }>("/api/settings/language")
      .then(({ language }) => {
        if (language !== initial) {
          setCurrentLanguage(language);
          setLangState(language);
          localStorage.setItem(STORAGE_KEY, language);
          document.documentElement.lang = language;
        }
      })
      .catch(() => undefined); // backend giù: si resta sulla lingua locale
    return () => cancelAnimationFrame(raf);
  }, []);

  const setLang = (next: Language) => {
    setCurrentLanguage(next);
    setLangState(next);
    localStorage.setItem(STORAGE_KEY, next);
    document.documentElement.lang = next;
    apiPut("/api/settings/language", { language: next }).catch(() => undefined);
  };

  return (
    <I18nContext.Provider value={{ lang, t: DICTIONARIES[lang], setLang }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useT(): Dictionary {
  return useContext(I18nContext).t;
}

export function useI18n() {
  return useContext(I18nContext);
}
