"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getProbe, setSetupCompleted, errText } from "@/lib/api";
import { passiDelWizard, type Passo } from "@/lib/setup-steps";
import { Alert, Button } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { WelcomeStep } from "@/components/setup/steps/welcome";
import { PrerequisitesStep } from "@/components/setup/steps/prerequisites";
import { LibraryStep } from "@/components/setup/steps/library";
import { ServicesStep } from "@/components/setup/steps/services";
import { SummaryStep } from "@/components/setup/steps/summary";

/* Configurazione guidata: nessun passo è bloccante. Lo stato di completamento
   vive nel backend (AppState), non in localStorage: è una proprietà
   dell'installazione, non del browser.

   I passi non sono sempre cinque: nell'app impacchettata ffmpeg e fpcalc
   viaggiano dentro il bundle, quindi il passo dei prerequisiti non ha niente
   da chiedere e non si monta (vedi lib/setup-steps.ts). slskd non è mai stato
   un passo suo e ora non è nemmeno un prerequisito: è un servizio, e si
   configura dal passo Servizi — vedi components/slskd-row.tsx. */

export default function SetupPage() {
  const t = useT();
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [componenti, setComponenti] = useState<{ present: boolean; source: string | null }[] | null>(null);

  useEffect(() => {
    let vivo = true;
    getProbe()
      .then((r) => {
        if (vivo) setComponenti(r.components);
      })
      .catch(() => {
        // Il probe che non risponde non deve togliere un passo: `null` lo
        // tiene, ed e' la scelta prudente.
        if (vivo) setComponenti(null);
      });
    return () => {
      vivo = false;
    };
  }, []);

  const STEPS = passiDelWizard(componenti);
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

  const titolo: Record<Passo, string> = {
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
        <p className="mt-1 text-sm text-muted">{t.setup.subtitle(STEPS.length)}</p>
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
