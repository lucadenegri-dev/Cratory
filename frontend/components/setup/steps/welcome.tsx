"use client";

import { useI18n, useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

export function WelcomeStep() {
  const t = useT();
  const { lang, setLang } = useI18n();
  return (
    <div className="space-y-6">
      <p className="text-sm leading-relaxed text-muted">{t.setup.welcomeBody}</p>
      <div>
        <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.setup.languageLabel}</div>
        <div role="group" className="inline-flex border border-border bg-surface p-1">
          {(["it", "en"] as const).map((code) => (
            <button
              key={code}
              type="button"
              aria-pressed={lang === code}
              onClick={() => setLang(code)}
              className={cn("px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
                lang === code ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
            >
              {code}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
