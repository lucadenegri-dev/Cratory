"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { setSetupCompleted, errText } from "@/lib/api";
import { Alert, Button } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { WelcomeStep } from "@/components/setup/steps/welcome";
import { PrerequisitesStep } from "@/components/setup/steps/prerequisites";
import { LibraryStep } from "@/components/setup/steps/library";
import { ServicesStep } from "@/components/setup/steps/services";
import { SummaryStep } from "@/components/setup/steps/summary";

/* Configurazione guidata: cinque passi, nessuno bloccante. Lo stato di
   completamento vive nel backend (AppState), non in localStorage: è una
   proprietà dell'installazione, non del browser. Slskd non ha più un passo
   suo: la sua riga nei prerequisiti (ComponentRow) chiede le credenziali e
   installa da sola quando il demone non risponde già — vedi
   component-row.tsx. */
const STEPS = ["welcome", "prerequisites", "library", "services", "summary"] as const;

export default function SetupPage() {
  const t = useT();
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const step = STEPS[index];

  const esci = useCallback(async () => {
    setError(null);
    try {
      await setSetupCompleted(true);
      router.replace("/");
    } catch (e) {
      /* Scrittura fallita: il flag resta false sul backend. Se si naviga
         comunque via, il prossimo giro il gate riporta qui senza spiegazione
         (trappola ritardata) — si resta sul wizard e si mostra l'errore. */
      setError(errText(e));
    }
  }, [router]);

  const titolo: Record<(typeof STEPS)[number], string> = {
    welcome: t.setup.welcomeTitle,
    prerequisites: t.setup.prereqTitle,
    library: t.setup.libraryTitle,
    services: t.setup.servicesTitle,
    summary: t.setup.summaryTitle,
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 py-10">
      <header className="mb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-lg font-semibold uppercase tracking-wide text-fg-strong">{t.setup.title}</h1>
          <span className="tnum text-xs text-faint">{t.setup.stepOf(index + 1, STEPS.length)}</span>
        </div>
        <p className="mt-1 text-sm text-muted">{t.setup.subtitle}</p>
      </header>

      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-fg-strong">{titolo[step]}</h2>

      <div className="flex-1">
        {step === "welcome" && <WelcomeStep />}
        {step === "prerequisites" && <PrerequisitesStep />}
        {step === "library" && <LibraryStep />}
        {step === "services" && <ServicesStep />}
        {step === "summary" && <SummaryStep />}
      </div>

      {error && <Alert tone="danger">⚠ {error}</Alert>}

      <footer className="mt-10 flex items-center justify-between gap-4 border-t border-border pt-5">
        <button type="button" onClick={esci} className="text-xs text-muted underline-offset-4 hover:underline">
          {t.setup.skipAll}
        </button>
        <div className="flex gap-2">
          {index > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setIndex((i) => i - 1)}>{t.setup.back}</Button>
          )}
          {index < STEPS.length - 1 ? (
            <Button size="sm" variant="outline" onClick={() => setIndex((i) => i + 1)}>{t.setup.next}</Button>
          ) : (
            <Button size="sm" onClick={esci}>{t.setup.finish}</Button>
          )}
        </div>
      </footer>
    </div>
  );
}
