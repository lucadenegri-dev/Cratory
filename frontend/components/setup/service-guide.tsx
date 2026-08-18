"use client";

import { useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { ServiceKey } from "@/lib/setup-services";

/* La guida "come si attiva questa API": passi numerati, link al provider e,
   dove serve, un valore da copiare incastonato nel passo che lo richiede
   (il redirect URI di Spotify sta nel terzo passo, non in fondo). */
export function ServiceGuide({ service, copyValue, docsUrl, copyAfterStep = 2 }: {
  service: ServiceKey;
  copyValue?: string | null;
  docsUrl: string;
  copyAfterStep?: number;
}) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const guide = t.setup.guides[service];

  const copy = async () => {
    if (!copyValue) return;
    await navigator.clipboard.writeText(copyValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="border border-border bg-bg p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[10px] uppercase tracking-wider text-muted">{t.setup.howTo}</span>
        <a href={docsUrl} target="_blank" rel="noreferrer">
          <Button size="sm" variant="ghost">
            <ExternalLink size={14} /> {t.setup.openProvider}
          </Button>
        </a>
      </div>
      <ol className="space-y-1.5">
        {guide.steps.map((step, i) => (
          <li key={i}>
            <p className="flex gap-2 text-sm text-muted">
              <span className="tnum text-faint">{String(i + 1).padStart(2, "0")}</span>
              <span>{step}</span>
            </p>
            {copyValue && i === copyAfterStep && (
              <div className="ml-7 mt-1.5 flex items-center gap-2">
                <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">{copyValue}</code>
                <Button size="sm" variant="outline" onClick={copy}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? t.setup.copied : t.setup.copyValue}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-3 border-l-2 border-border pl-3 text-xs text-faint">{guide.note}</p>
    </div>
  );
}
