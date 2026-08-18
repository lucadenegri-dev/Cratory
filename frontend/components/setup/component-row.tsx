"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { errText, getInstallStatus, startInstall, type InstallStatus, type ProbeComponent } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Una riga del probe. I componenti auto-installabili hanno il bottone; gli
   altri mostrano il comando da eseguire a mano, con copia. */
export function ComponentRow({ c, onChanged }: { c: ProbeComponent; onChanged: () => void }) {
  const t = useT();
  const [install, setInstall] = useState<InstallStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* Pulisci sia l'intervallo di polling che il timeout di copia se il componente si smonta. */
  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);

  const run = async () => {
    setError(null);
    try {
      setInstall(await startInstall(c.key));
    } catch (e) {
      setError(errText(e));
      return;
    }
    timer.current = setInterval(async () => {
      try {
        const st = await getInstallStatus();
        setInstall(st);
        if (st.status !== "running") {
          if (timer.current) clearInterval(timer.current);
          onChanged();
        }
      } catch (e) {
        setError(errText(e));
        if (timer.current) clearInterval(timer.current);
      }
    }, 1000);
  };

  const copy = async () => {
    if (!c.install_command) return;
    await navigator.clipboard.writeText(c.install_command.join(" "));
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setCopied(true);
    timeoutRef.current = setTimeout(() => setCopied(false), 1500);
  };

  const running = install?.status === "running" && install.key === c.key;
  const label = t.setup.components[c.key as keyof typeof t.setup.components] ?? c.key;

  return (
    <div className="border-b border-border p-4 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{c.key}</span>
            <span className="text-[10px] uppercase tracking-wider text-faint">
              {c.severity === "required" ? t.setup.severityRequired : t.setup.severityOptional}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted">{label}</p>
          <p className="mt-1 text-xs text-faint">
            {t.setup.unlocksLabel}{" "}
            {c.unlocks.map((u) => t.setup.unlocks[u as keyof typeof t.setup.unlocks] ?? u).join(", ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className={`text-[10px] uppercase tracking-wider ${c.present ? "text-fg-strong" : "text-muted"}`}>
            {c.present ? (c.version ? t.setup.detected(c.version) : t.setup.installDone) : t.setup.notFound}
          </div>
          {c.source === "bundle" && <div className="text-[10px] text-faint">{t.setup.fromBundle}</div>}
        </div>
      </div>

      {!c.present && c.auto_installable && (
        <div className="mt-3">
          <Button size="sm" variant="outline" disabled={running} onClick={run}>
            {running ? t.setup.installing : t.setup.installButton}
          </Button>
          {install && install.key === c.key && install.log.length > 0 && (
            <pre className="mt-2 max-h-40 overflow-auto bg-elevated p-2 text-[11px] leading-snug text-muted">
              {install.log.join("\n")}
            </pre>
          )}
          {install?.status === "error" && (
            <p className="mt-1 text-xs text-danger">{t.setup.installFailed} — {install.detail}</p>
          )}
          {error && <p className="mt-1 text-xs text-danger">{error}</p>}
        </div>
      )}

      {!c.present && !c.auto_installable && c.install_command && (
        <div className="mt-3">
          <p className="mb-1 text-xs text-muted">{t.setup.installManual}</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">
              {c.install_command.join(" ")}
            </code>
            <Button size="sm" variant="outline" onClick={copy}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? t.setup.copied : t.setup.copyCommand}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
