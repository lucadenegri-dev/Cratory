"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiGet, servicesStatus, setSetupCompleted, type ServiceStatus, type SpotifyStatus } from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ConfigCard } from "@/components/settings/config-card";
import { OrganizeSection } from "@/components/settings/organize-section";
import { ServicesList } from "@/components/settings/services-list";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/cn";

/* Impostazioni: 4 gruppi (fusione F1-F6, un prodotto solo).
   Generale · Percorsi e libreria · Servizi esterni · Organize. */

function SettingsInner() {
  const { lang, setLang, t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const oauth = params.get("spotify");
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    servicesStatus().then((r) => { setServices(r.services); setError(null); }).catch((e) => { setServices(null); setError(String(e.message ?? e)); });
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch(() => setSpotify(null));
  }, []);
  useEffect(load, [load]);

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{t.settings.marginaliaPrefix} <code className="rounded-none bg-elevated px-1">backend/.env</code> {t.settings.marginaliaSuffix}</p>
    </div>
  );

  return (
    <PageLayout title={t.settings.pageTitle} marginaliaTitle={t.settings.helpTitle} marginalia={marginalia}>
      {oauth === "connected" && <div className="mb-4"><Alert tone="info">{t.settings.spotifyConnected}</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">{t.settings.spotifyLoginFailed(params.get("detail") ?? "")}</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">{t.dashboard.backendDown(error)}</Alert></div>}

      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.settings.languageLabel}</div>
      <div className="border border-border p-5">
        <div role="group" aria-label={t.settings.languageLabel} className="inline-flex rounded-none border border-border bg-surface p-1">
          <button
            type="button"
            aria-pressed={lang === "it"}
            onClick={() => setLang("it")}
            className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              lang === "it" ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
          >
            {t.settings.languageIt}
          </button>
          <button
            type="button"
            aria-pressed={lang === "en"}
            onClick={() => setLang("en")}
            className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              lang === "en" ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
          >
            {t.settings.languageEn}
          </button>
        </div>
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.pathsHeading}</div>
      <ConfigCard />

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.servicesHeading}</div>
      {services ? <ServicesList services={services} spotify={spotify} /> : (
        <div className="border border-border">{!error && <div className="px-5"><Loading /></div>}</div>
      )}
      <div className="mt-4">
        <Button size="sm" variant="outline" onClick={async () => {
          await setSetupCompleted(false);
          router.push("/setup");
        }}>
          {t.setup.reopen}
        </Button>
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.nav.groupOrganize}</div>
      <OrganizeSection />
    </PageLayout>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
