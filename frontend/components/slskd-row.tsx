"use client";

/* slskd, dall'inizio alla fine, in un posto solo.
 *
 * Prima questo percorso era diviso in due: il wizard sapeva scaricare il
 * binario e scrivere la configurazione, Impostazioni sapeva collegare e
 * avviare — e la riga di Impostazioni, quando il binario mancava, rimandava
 * al wizard perche' davvero non sapeva installarlo. Non erano due copie della
 * stessa cosa: erano due meta'. Qui stanno insieme e mostrano UNA azione,
 * quella che ha senso adesso. */

import { useCallback, useEffect, useState } from "react";
import { Plug, Unplug } from "lucide-react";
import {
  daemonConfig, daemonStart, daemonStatus, daemonStop, errText, getInstallStatus,
  slskdConnect, slskdDisconnect, slskdStatus, startInstall,
  type SlskdDaemonStatus, type SlskdStatus,
} from "@/lib/api";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";

type Fase = "caricamento" | "scarica" | "configura" | "avvia" | "collega" | "collegato";

function fase(d: SlskdDaemonStatus | null, s: SlskdStatus | null): Fase {
  if (!d) return "caricamento";
  if (!d.installed) return "scarica";
  if (!d.configured) return "configura";
  if (!d.reachable) return "avvia";
  return s?.is_connected && s?.is_logged_in ? "collegato" : "collega";
}

/* Tre possibilita', non due: `owned` e' un tristate. `null` significa che su
   questa piattaforma non si puo' stabilire chi ha avviato il demone, e non va
   spacciato per "non nostro" -- e' anche la ragione per cui il bottone Ferma
   compare solo quando la risposta e' un si' pieno. */
function etichettaDemone(d: SlskdDaemonStatus, t: Dictionary): string {
  if (!d.reachable) return t.setup.daemonStopped;
  if (d.owned === true) return t.setup.daemonRunning;
  if (d.owned === false) return t.setup.daemonRunningElsewhere;
  return t.setup.daemonRunningUnknownOwner;
}

export function SlskdRow() {
  const t = useT();
  const [daemon, setDaemon] = useState<SlskdDaemonStatus | null>(null);
  const [slskd, setSlskd] = useState<SlskdStatus | null>(null);
  const [utente, setUtente] = useState("");
  const [password, setPassword] = useState("");
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  const ricarica = useCallback(async () => {
    try {
      setDaemon(await daemonStatus());
    } catch (e) {
      setErrore(errText(e));
    }
    // Lo stato del login non e' raggiungibile finche' il demone non risponde:
    // il suo fallimento qui non e' una notizia, e' la normalita' delle prime
    // fasi.
    slskdStatus().then(setSlskd).catch(() => setSlskd(null));
  }, []);

  useEffect(() => { void ricarica(); }, [ricarica]);

  const azione = async (fn: () => Promise<unknown>) => {
    setInCorso(true);
    setErrore(null);
    try {
      await fn();
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setInCorso(false);
      await ricarica();
    }
  };

  const scarica = () =>
    azione(async () => {
      await startInstall("slskd");
      let stato = await getInstallStatus();
      while (stato.status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
        stato = await getInstallStatus();
      }
      if (stato.status === "error") throw new Error(stato.detail ?? "");
    });

  const salva = () =>
    azione(async () => {
      await daemonConfig({ username: utente, password });
      setPassword(""); // non resta in memoria oltre l'invio
    });

  const f = fase(daemon, slskd);
  // Solo un si' pieno autorizza a fermarlo: un demone acceso da qualcun altro
  // non e' nostro da spegnere, e uno di proprieta' ignota nemmeno.
  const possiamoFermarlo = daemon?.owned === true;

  return (
    <div className="mt-3 border border-border bg-bg p-3">
      {f === "caricamento" && <Spinner />}

      {f === "scarica" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepDownload}</p>
          <Button size="sm" disabled={inCorso} onClick={scarica}>
            {inCorso ? t.settings.slskdDownloading : t.settings.slskdDownload}
          </Button>
        </div>
      )}

      {f === "configura" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepConfigure}</p>
          <Input value={utente} onChange={(e) => setUtente(e.target.value)}
                 placeholder={t.setup.daemonUsername} disabled={inCorso} />
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 placeholder={t.setup.daemonPassword} disabled={inCorso} />
          <Button size="sm" disabled={inCorso || !utente || !password} onClick={salva}>
            {inCorso ? t.settings.slskdSaving : t.settings.slskdSaveConfig}
          </Button>
        </div>
      )}

      {f === "avvia" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepStart}</p>
          {daemon?.username && (
            <p className="text-xs text-faint">{t.settings.soulseekConnectedAs(daemon.username)}</p>
          )}
          <Button size="sm" disabled={inCorso} onClick={() => azione(daemonStart)}>
            {t.setup.daemonStart}
          </Button>
        </div>
      )}

      {(f === "collega" || f === "collegato") && daemon && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-fg-strong">
              {f === "collegato"
                ? (slskd?.username
                    ? t.settings.soulseekConnectedAs(slskd.username)
                    : t.settings.soulseekConnected)
                : t.settings.slskdStepConnect}
            </span>
            <div className="flex gap-2">
              {f === "collegato" ? (
                <Button size="sm" variant="outline" disabled={inCorso}
                        onClick={() => azione(slskdDisconnect)}>
                  <Unplug size={14} /> {t.settings.soulseekDisconnect}
                </Button>
              ) : (
                <Button size="sm" disabled={inCorso} onClick={() => azione(slskdConnect)}>
                  <Plug size={14} /> {t.settings.soulseekConnect}
                </Button>
              )}
              {possiamoFermarlo && (
                <Button size="sm" variant="outline" disabled={inCorso}
                        onClick={() => azione(daemonStop)}>
                  {t.setup.daemonStop}
                </Button>
              )}
            </div>
          </div>
          <p className="text-[10px] uppercase tracking-wider text-muted">
            {etichettaDemone(daemon, t)}
          </p>
        </div>
      )}

      {errore && <Alert tone="danger">{errore}</Alert>}
    </div>
  );
}
