"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import {
  errText, getConfigSettings, servicesStatus, spotifyLoginUrl,
  type ConfigSettings, type ServiceStatus,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { ServiceKey } from "@/lib/setup-services";
import { ServiceCard } from "../service-card";
import { SlskdRow } from "@/components/slskd-row";
import { PathField } from "../path-field";

/* slskd sta qui e non piu' fra i prerequisiti: non e' un binario da avere ma
   un servizio da configurare, e la sua riga sa fare tutto il percorso —
   scaricare il demone, scrivergli la configurazione, avviarlo, collegarsi. */
const ORDINE: ServiceKey[] = ["spotify", "anthropic", "discogs", "acoustid", "slskd"];

export function ServicesStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings()
      .then((config) => {
        setError(null);
        setConfig(config);
      })
      .catch((e) => setError(errText(e)));
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
          {service === "slskd" && <SlskdRow />}
          <ServiceCard
            service={service}
            secrets={config.secrets}
            redirectUri={config.spotify_redirect_uri}
            docsUrl={docs(service)}
            onSaved={load}
          >
            {service === "spotify" && config.secrets.spotify_client_id.configured && config.secrets.spotify_client_secret.configured && (
              <a href={spotifyLoginUrl()}>
                <Button size="sm" variant="outline">
                  <ExternalLink size={14} /> {t.settings.connectButton}
                </Button>
              </a>
            )}
            {/* ai_model non è un segreto (torna in chiaro come gli altri campi
                di config): stesso PathField dei percorsi, non una terza
                variante di campo solo per questo. */}
            {service === "anthropic" && (
              <PathField
                fieldKey="ai_model"
                label={t.setup.aiModelLabel}
                value={config.ai_model.value}
                detail={config.ai_model.detail ?? t.setup.aiModelHint}
                canPick={false}
                kind="text"
                onSaved={setConfig}
              />
            )}
          </ServiceCard>
        </section>
      ))}
    </div>
  );
}
