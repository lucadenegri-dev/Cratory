"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import {
  daemonConfig, daemonStart, errText, getInstallStatus, startInstall,
  type InstallStatus, type ProbeComponent,
} from "@/lib/api";
import { Alert, Button, Field, Input } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Una riga del probe. I componenti auto-installabili hanno il bottone; gli
   altri mostrano il comando da eseguire a mano, con copia — e lo stesso
   comando manuale ricompare per un componente auto-installabile se
   l'installazione appena tentata è fallita: è la via di fuga (es. Essentia
   fuori dalla combinazione CPython/piattaforma per cui esiste la wheel).

   Il demone (slskd) è un caso a parte, gestito qui per intero invece che in
   un passo dedicato: se risponde già, la riga si limita a dire che le sue
   impostazioni vivono altrove (Impostazioni le duplica già: URL, cartella
   download, chiave API, avvio/arresto); se non risponde, servono le
   credenziali Soulseek PRIMA di poter installare — a differenza di ffmpeg e
   fpcalc non basta un bottone Installa, quindi la riga stessa chiede
   username e password e fa scaricare, configurare e avviare in un solo
   passaggio. */
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

  // Stato del form credenziali del demone (solo slskd): username/password
  // Soulseek, non un secondo `install` locale — il giro composito qui sotto
  // non passa dallo stesso stato "running/error" del bottone Installa
  // ordinario (quello aggiorna log/percentuale a ogni poll; questo aspetta e
  // basta), quindi tenerli separati evita che l'uno interferisca sui rami
  // JSX dell'altro.
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [avvioDemone, setAvvioDemone] = useState(false);
  const [erroreDemone, setErroreDemone] = useState<string | null>(null);

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

  // Scarica il binario del demone, scrive le credenziali nel suo file di
  // configurazione e lo avvia — stessa logica e stesso ordine che aveva il
  // passo dedicato del wizard (ora sparito): configura PRIMA di scaricare
  // (le credenziali servono comunque), poi installa, poi avvia solo se
  // l'installazione non è finita in errore.
  const installaDemone = async () => {
    setErroreDemone(null);
    setAvvioDemone(true);
    busy.current = true;
    onBusyChange?.(true);
    try {
      await daemonConfig({ username, password });
      if (!mounted.current) return;
      setPassword(""); // non resta in memoria oltre l'invio
      await startInstall(c.key);
      if (!mounted.current) return;
      let stato = await getInstallStatus();
      while (mounted.current && stato.status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
        if (!mounted.current) return;
        stato = await getInstallStatus();
      }
      if (!mounted.current) return;
      // Un job che finisce in errore (checksum sbagliato, rete caduta) non
      // deve far scattare l'avvio: senza questo controllo si proverebbe
      // comunque ad avviare — "slskd non è installato" se non c'era prima,
      // oppure, peggio, l'avvio silenzioso di una copia vecchia già presente.
      if (stato.status === "error") {
        // checksum_mismatch e unsafe_archive sono un allarme, non un intoppo
        // (design doc §7): stessa distinzione delle altre righe, qui per il
        // download del binario slskd stesso.
        setErroreDemone(
          stato.error_code === "checksum_mismatch" ? t.setup.installFailedChecksum
          : stato.error_code === "unsafe_archive" ? t.setup.installFailedArchive
          : stato.detail,
        );
        return;
      }
      await daemonStart();
      if (!mounted.current) return;
      onChanged();
    } catch (e) {
      if (mounted.current) setErroreDemone(errText(e));
    } finally {
      if (mounted.current) setAvvioDemone(false);
      busy.current = false;
      onBusyChange?.(false);
    }
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
  // Le ricette di sistema sono scritte per un gestore di pacchetti preciso.
  // Su macOS è Homebrew, che NON è preinstallato: senza dirlo, il comando è
  // inutilizzabile proprio per chi parte da zero.
  const needsBrew = c.install_command?.[0] === "brew";

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
          {c.docs && (
            <a href={c.docs} target="_blank" rel="noreferrer"
               className="mt-1 inline-block text-xs text-fg underline-offset-4 hover:underline">
              {t.setup.docsLink} ↗
            </a>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className={`text-[10px] uppercase tracking-wider ${c.present ? "text-fg-strong" : "text-muted"}`}>
            {c.present ? (c.version ? t.setup.detected(c.version) : t.setup.installDone) : t.setup.notFound}
          </div>
          {c.source === "bundle" && <div className="text-[10px] text-faint">{t.setup.fromBundle}</div>}
          {c.shadowing && <div className="text-[10px] text-faint">{t.setup.shadowingSystem(c.shadowing)}</div>}
        </div>
      </div>

      {/* Demone già raggiungibile: niente da offrire, solo dire dove sta la
          sua configurazione — frase generica apposta (nessun "passo 1", nessun
          "qui sotto"): è vera anche letta dalla pagina Impostazioni. */}
      {c.present && c.kind === "daemon" && (
        <p className="mt-3 text-xs text-muted">{t.setup.daemonManagedElsewhere}</p>
      )}

      {/* Demone non raggiungibile: servono le credenziali Soulseek prima di
          poter installare, quindi niente bottone Installa nudo come per
          ffmpeg/fpcalc — la riga chiede username e password e fa tutto lei. */}
      {!c.present && c.kind === "daemon" && (
        <div className="mt-3 space-y-2">
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted">{t.setup.daemonTitle}</p>
          <Field label={t.setup.daemonUsername}>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} disabled={disabled || avvioDemone} />
          </Field>
          <Field label={t.setup.daemonPassword}>
            <Input type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)} disabled={disabled || avvioDemone} />
          </Field>
          <p className="text-xs text-faint">{t.setup.daemonCredentialsNote}</p>
          <Button size="sm" variant="outline"
                  disabled={disabled || avvioDemone || !username || !password}
                  onClick={installaDemone}>
            {avvioDemone ? t.setup.daemonStarting : t.setup.daemonInstallAndStart}
          </Button>
          {erroreDemone && <Alert tone="danger">{erroreDemone}</Alert>}
        </div>
      )}

      {!c.present && c.installable && c.kind !== "daemon" && (
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
              {/* checksum_mismatch e unsafe_archive sono un allarme, non un
                  intoppo (design doc §7): frase propria che scoraggia il
                  "riprova e spera", non il generico installFailed. */}
              <p className="text-xs text-danger">
                {install?.error_code === "checksum_mismatch" ? t.setup.installFailedChecksum
                  : install?.error_code === "unsafe_archive" ? t.setup.installFailedArchive
                  : t.setup.installFailed}
              </p>
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
          fuori dalla combinazione CPython/piattaforma pinnata). Il demone ha
          il suo blocco dedicato sopra, mai questo. */}
      {!c.present && c.kind !== "daemon" && c.install_command && (!c.auto_installable || failed) && (
        <div className="mt-3">
          {!c.installable && <p className="mb-1 text-xs text-muted">{t.setup.installNoBuild}</p>}
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
          {needsBrew && (
            <p className="mt-1.5 text-[11px] text-faint">
              {t.setup.installNeedsBrew}{" "}
              <a href="https://brew.sh" target="_blank" rel="noreferrer"
                 className="text-fg underline-offset-4 hover:underline">
                {t.setup.installGetBrew} ↗
              </a>
            </p>
          )}
        </div>
      )}

      {/* Nessuna ricetta e non è il demone (che ha il suo blocco dedicato
          sopra): dire che non esiste un comando è un'informazione, non
          un'assenza. */}
      {!c.present && c.kind !== "daemon" && !c.install_command && (
        <p className="mt-3 text-xs text-muted">{t.setup.installNoRecipe}</p>
      )}
    </div>
  );
}
