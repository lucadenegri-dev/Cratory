"use client";

import { useEffect, useState } from "react";

import { errText, getDiscoverySettings, setDiscoverySettings } from "@/lib/api";
import { Alert, Checkbox, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Il gruppo Discovery delle Impostazioni: per ora una sola preferenza, Discogs
   come sorgente nella barra del Dig. È presentazione: il backend accetta
   source=discogs comunque, e Organize col suo client Discogs non c'entra. */
export function DiscoverySection() {
  const t = useT();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDiscoverySettings()
      .then((s) => setEnabled(s.discogs_enabled))
      .catch((e) => setError(errText(e)));
  }, []);

  const toggle = async (v: boolean) => {
    setError(null);
    try {
      setEnabled((await setDiscoverySettings({ discogs_enabled: v })).discogs_enabled);
    } catch (e) {
      setError(errText(e));
    }
  };

  return (
    <div className="border border-border p-5">
      {error && <div className="mb-3"><Alert tone="danger">{error}</Alert></div>}
      {enabled === null && !error ? <Loading /> : enabled !== null && (
        <>
          <Checkbox label={t.settings.discoveryDiscogs} checked={enabled} onChange={toggle} />
          <p className="mt-1 text-xs text-faint">{t.settings.discoveryDiscogsHint}</p>
        </>
      )}
    </div>
  );
}
