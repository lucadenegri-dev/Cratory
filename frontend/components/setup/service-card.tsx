"use client";

import { useState, type ReactNode } from "react";
import { errText, testCredential, type CredentialTestResult, type SecretKey, type SecretState } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";
import { SERVICE_FIELDS, TESTABLE, type ServiceKey } from "@/lib/setup-services";
import { CredentialField } from "./credential-field";
import { ServiceGuide } from "./service-guide";

/* Guida + campi + prova. È l'unità condivisa fra il wizard (dove sta dentro un
   passo, in sequenza) e Impostazioni (dove sta dentro una riga espandibile):
   una sola implementazione, due inquadrature. */

function esitoTesto(res: CredentialTestResult, t: Dictionary): string {
  if (res.code === "no_token") return t.setup.testNoToken;
  if (res.code === "not_configured") return t.setup.testNotConfigured;
  if (res.code === "fpcalc_missing") return t.setup.testFpcalcMissing;
  if (res.code === "network_error") return `${t.setup.testNetworkError} — ${res.detail}`;
  if (res.ok) return res.detail ? `${t.setup.testOk} — ${res.detail}` : t.setup.testOk;
  return `${t.setup.testKo} — ${res.detail}`;
}

export function ServiceCard({ service, secrets, redirectUri, docsUrl, onSaved, children }: {
  service: ServiceKey;
  secrets: Record<SecretKey, SecretState> | undefined;
  redirectUri?: string | null;
  docsUrl: string;
  onSaved: () => void;
  children?: ReactNode;
}) {
  const t = useT();
  const [result, setResult] = useState<CredentialTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  const runTest = async () => {
    setTesting(true);
    try {
      setResult(await testCredential(service));
    } catch (e) {
      setResult({ ok: false, code: "network_error", detail: errText(e) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-3">
      <ServiceGuide
        service={service}
        docsUrl={docsUrl}
        copyValue={service === "spotify" ? redirectUri : null}
      />
      <div>
        {SERVICE_FIELDS[service].map((key) => (
          <CredentialField
            key={key}
            fieldKey={key}
            label={t.setup.fieldLabels[key]}
            state={secrets?.[key]}
            onSaved={onSaved}
          />
        ))}
      </div>
      {children}
      {TESTABLE.includes(service) && (
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant="outline" disabled={testing} onClick={runTest}>
            {testing ? t.setup.testing : t.setup.testButton}
          </Button>
          {result && (
            <span className={`text-xs ${result.ok ? "text-fg-strong" : "text-danger"}`}>
              {esitoTesto(result, t)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
