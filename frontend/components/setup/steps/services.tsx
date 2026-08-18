"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import {
  errText, getConfigSettings, servicesStatus, SPOTIFY_LOGIN_URL,
  type ConfigSettings, type ServiceStatus,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { ServiceKey } from "@/lib/setup-services";
import { ServiceCard } from "../service-card";

const ORDINE: ServiceKey[] = ["spotify", "anthropic", "discogs", "acoustid"];

export function ServicesStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings().then(setConfig).catch((e) => setError(errText(e)));
    servicesStatus().then((r) => setServices(r.services)).catch(() => setServices([]));
  }, []);

  useEffect(() => load(), [load]);

  if (!config || !services) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  const docs = (key: string) => services.find((s) => s.key === key)?.docs ?? "";

  return (
    <div className="space-y-8">
      <p className="text-sm leading-relaxed text-muted">{t.setup.servicesBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      {ORDINE.map((service) => (
        <section key={service} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-fg-strong">
            {t.setup.guides[service].title}
          </h3>
          <ServiceCard
            service={service}
            secrets={config.secrets}
            redirectUri={config.spotify_redirect_uri}
            docsUrl={docs(service)}
            onSaved={load}
          >
            {service === "spotify" && config.secrets.spotify_client_id.configured && (
              <a href={SPOTIFY_LOGIN_URL}>
                <Button size="sm" variant="outline">
                  <ExternalLink size={14} /> {t.settings.connectButton}
                </Button>
              </a>
            )}
          </ServiceCard>
        </section>
      ))}
    </div>
  );
}
