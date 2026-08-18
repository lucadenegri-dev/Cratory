"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { errText, getInstallStatus, startInstall, type InstallStatus, type ProbeComponent } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Una riga del probe. I componenti auto-installabili hanno il bottone; gli
   altri mostrano il comando da eseguire a mano, con copia — e lo stesso
   comando manuale ricompare per un componente auto-installabile se
   l'installazione appena tentata è fallita: è la via di fuga (es. Essentia
   fuori dalla combinazione CPython/piattaforma per cui esiste la wheel). */
export function ComponentRow({ c, onChanged, disabled, onBusyChange }: {
  c: ProbeComponent;
  onChanged: () => void;
  /* Un altro componente sta installando: disabilita il bottone di QUESTA riga
     (il backend accetta un solo install alla volta, 409 altrimenti). */
  disabled?: boolean;
  /* Notifica il genitore quando QUESTA riga inizia/finisce un'installazione,
     cosi' PrerequisitesStep sa quale bottone disabilitare altrove senza un
     secondo polling: riusa quello che questo componente fa già. */
  onBusyChange?: (busy: boolean) => void;
}) {
  const t = useT();
  const [install, setInstall] = useState<InstallStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);
  // true quando è QUESTA riga ad aver segnalato busy al genitore: serve a
  // rilasciare il lucchetto allo smontaggio senza toccare quello di un'altra riga.
  const busy = useRef(false);
  // Copia sempre aggiornata di onBusyChange, letta dalla cleanup dell'effetto
  // di smontaggio (che gira una volta sola, deps []): senza questa "ultima
  // versione" richiamerebbe la prop del render iniziale, non quella corrente.
  const onBusyChangeRef = useRef(onBusyChange);
  useEffect(() => {
    onBusyChangeRef.current = onBusyChange;
  });

  /* Pulisci sia l'intervallo di polling che il timeout di copia se il componente si smonta.
     Se lo smontaggio arriva a metà installazione (il polling non ha ancora
     raggiunto uno stato terminale), il lucchetto `busyKey` del genitore
     resterebbe agganciato per sempre a una riga che non esiste più: nessun
     altro bottone Installa si riabiliterebbe finché non si lascia e si
     rientra nello step. Rilascialo qui, ma solo se è ancora questa riga a
     detenerlo. */
  useEffect(() => () => {
    mounted.current = false;
    if (timer.current) clearInterval(timer.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (busy.current) {
      busy.current = false;
      onBusyChangeRef.current?.(false);
    }
  }, []);

  const run = async () => {
    setError(null);
    let status: InstallStatus;
    try {
      status = await startInstall(c.key);
    } catch (e) {
      if (!mounted.current) return;
      setError(errText(e));
      return;
    }
    // La riga potrebbe essersi smontata mentre l'installazione partiva:
    // niente stato, niente lucchetto, niente polling che nessuno pulirebbe.
    if (!mounted.current) return;
    setInstall(status);
    busy.current = true;
    onBusyChange?.(true);
    timer.current = setInterval(async () => {
      try {
        const st = await getInstallStatus();
        setInstall(st);
        if (st.status !== "running") {
          if (timer.current) clearInterval(timer.current);
          busy.current = false;
          onBusyChange?.(false);
          onChanged();
        }
      } catch (e) {
        setError(errText(e));
        if (timer.current) clearInterval(timer.current);
        busy.current = false;
        onBusyChange?.(false);
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
  const failed = install?.status === "error" && install.key === c.key;
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
          <Button size="sm" variant="outline" disabled={running || disabled} onClick={run}>
            {running ? t.setup.installing : t.setup.installButton}
          </Button>
          {install && install.key === c.key && install.log.length > 0 && (
            <pre className="mt-2 max-h-40 overflow-auto bg-elevated p-2 text-[11px] leading-snug text-muted">
              {install.log.join("\n")}
            </pre>
          )}
          {failed && (
            <div className="mt-1">
              <p className="text-xs text-danger">{t.setup.installFailed}</p>
              {/* Il dettaglio grezzo del backend (es. "python è uscito con
                  codice 1") resta, ma come nota di debug secondaria: la
                  riga che guida l'utente è quella tradotta sopra. */}
              {install?.detail && <p className="mt-0.5 text-[11px] text-faint">{install.detail}</p>}
            </div>
          )}
          {error && <p className="mt-1 text-xs text-danger">{error}</p>}
        </div>
      )}

      {/* Il comando manuale è la via di fuga: sempre presente per i
          componenti non auto-installabili, e riappare per quelli
          auto-installabili appena l'installazione fallisce (es. Essentia
          fuori dalla combinazione CPython/piattaforma pinnata). */}
      {!c.present && c.install_command && (!c.auto_installable || failed) && (
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
