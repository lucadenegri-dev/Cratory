"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getLanguage, setLanguage } from "@/lib/organize/api";
import { en, type Dictionary } from "./en";
import { DICTIONARIES, STORAGE_KEY, setCurrentLanguage, type Language } from "./runtime";

export type { Dictionary, Language };
export { getCurrentLanguage, translateApiError } from "./runtime";

const I18nContext = createContext<{
  lang: Language;
  t: Dictionary;
  setLang: (next: Language) => void;
}>({ lang: "en", t: en, setLang: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>("en");

  useEffect(() => {
    /* localStorage evita il flash; il backend resta la fonte persistente. */
    const stored = localStorage.getItem(STORAGE_KEY);
    const initial: Language = stored === "it" ? "it" : "en";
    setCurrentLanguage(initial);
    document.documentElement.lang = initial;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLangState(initial);
    getLanguage()
      .then(({ language }) => {
        if (language !== initial) {
          setCurrentLanguage(language);
          setLangState(language);
          localStorage.setItem(STORAGE_KEY, language);
          document.documentElement.lang = language;
        }
      })
      .catch(() => undefined); // backend giù: si resta sulla lingua locale
  }, []);

  const setLang = (next: Language) => {
    setCurrentLanguage(next);
    setLangState(next);
    localStorage.setItem(STORAGE_KEY, next);
    document.documentElement.lang = next;
    setLanguage(next).catch(() => undefined);
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
