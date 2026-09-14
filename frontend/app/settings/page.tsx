"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { errText, servicesStatus, setSetupCompleted, type ServiceStatus } from "@/lib/api";
import { Alert, Button, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { BackupCard } from "@/components/settings/backup-card";
import { ConfigCard } from "@/components/settings/config-card";
import { DiscoverySection } from "@/components/settings/discovery-section";
import { OrganizeSection } from "@/components/settings/organize-section";
import { ServicesList } from "@/components/settings/services-list";
import { VersionCard } from "@/components/settings/version-card";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const SECTIONS = ["general", "library", "downloads", "connections", "backup"] as const;
// Intestazione di sezione del design system (DESIGN.md, «Label»).
const LABEL = "text-[10px] font-medium uppercase tracking-wider text-muted";

function SettingsInner() {
  const { lang, setLang, t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const oauth = params.get("spotify");
  const requested = params.get("section");
  const section = SECTIONS.find((s) => s === requested) ?? (oauth ? "connections" : "general");
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [setupBusy, setSetupBusy] = useState(false);

  const load = useCallback(() => {
    servicesStatus().then((r) => { setServices(r.services); setError(null); }).catch((e) => { setServices(null); setError(errText(e)); });
  }, []);
  useEffect(load, [load]);

  return (
    <PageLayout title={t.settings.pageTitle}>
      {/* Stessa grammatica della nav di sinistra (index-nav): uppercase
          tracciato, attiva sottolineata; la struttura è la hairline sotto. */}
      <nav aria-label={t.settings.pageTitle} className="mb-6 flex flex-wrap gap-x-6 gap-y-2 border-b border-border">
        {SECTIONS.map((key) => (
          <Link key={key} href={`/settings?section=${key}`} scroll={false}
            aria-current={section === key ? "page" : undefined}
            className={cn("py-3 text-xs uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg",
              section === key ? "text-fg-strong underline underline-offset-4" : "text-muted hover:text-fg")}>
            {t.settings.sections[key]}
          </Link>
        ))}
      </nav>
      <div className="max-w-4xl">
        {/* I pannelli restano montati (hidden, non smontati): cambiare sezione
            non deve perdere una bozza non salvata. */}
        <section hidden={section !== "general"} aria-label={t.settings.sections.general} className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5">
            <span className={LABEL}>{t.settings.languageLabel}</span>
            <div role="group" aria-label={t.settings.languageLabel}>
              <SegmentedControl value={lang} onChange={setLang}
                options={[{ value: "it", label: t.settings.languageIt }, { value: "en", label: t.settings.languageEn }]} />
            </div>
          </div>
          <DiscoverySection />
          <VersionCard />
          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-5">
            <div><h2 className={LABEL}>{t.settings.setupHeading}</h2><p className="mt-1 text-xs text-muted">{t.settings.setupHint}</p></div>
            <Button size="sm" variant="outline" disabled={setupBusy} onClick={async () => {
              setSetupBusy(true); setSetupError(null);
              try { await setSetupCompleted(false); router.push("/setup"); }
              catch (e) { setSetupError(errText(e)); setSetupBusy(false); }
            }}>{t.settings.setupButton}</Button>
          </div>
          {setupError && <Alert tone="danger">{setupError}</Alert>}
        </section>

        <div hidden={section !== "library" && section !== "downloads"}>
          <ConfigCard section={section === "downloads" ? "downloads" : "library"} />
          <div hidden={section !== "library"} className="mt-6">
            <details className="border-t border-border pt-4">
              <summary className={cn("cursor-pointer", LABEL)}>{t.settings.namingHeading}</summary>
              <div className="pt-5"><OrganizeSection /></div>
            </details>
          </div>
        </div>

        <section hidden={section !== "connections"} aria-label={t.settings.sections.connections}>
          <p className="mb-5 text-sm text-muted">{t.settings.connectionsHint}</p>
          {oauth === "connected" && <div className="mb-4"><Alert tone="info">{t.settings.spotifyConnected}</Alert></div>}
          {oauth === "error" && <div className="mb-4"><Alert tone="danger">{t.settings.spotifyLoginFailed(params.get("detail") ?? "")}</Alert></div>}
          {error && <div className="mb-4"><Alert tone="danger">{error}</Alert><Button className="mt-3" size="sm" variant="outline" onClick={load}>{t.settings.retryButton}</Button></div>}
          {services ? <ServicesList services={services} onServicesChanged={load} /> : !error && <Loading />}
        </section>

        <section hidden={section !== "backup"} aria-label={t.settings.sections.backup}>
          <p className="mb-5 text-sm text-muted">{t.settings.backupHint}</p>
          <BackupCard />
        </section>
      </div>
    </PageLayout>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
