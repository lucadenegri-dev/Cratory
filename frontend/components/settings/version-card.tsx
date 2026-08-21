"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { checkUpdates, errText, getAppVersion, type UpdateCheckResult } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* La versione in uso e il controllo degli aggiornamenti.

   Tre esiti e restano tre: aggiornato, disponibile, non verificabile. Il terzo
   ha il suo posto e il suo tono — presentarlo come "sei aggiornato" farebbe
   dire alla schermata una cosa che non sa. */
export function VersionCard() {
  const t = useT();
  const [versione, setVersione] = useState<string | null>(null);
  const [esito, setEsito] = useState<UpdateCheckResult | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    getAppVersion().then((r) => setVersione(r.version)).catch(() => setVersione(null));
  }, []);

  const controlla = async () => {
    setInCorso(true);
    setErrore(null);
    setEsito(null);
    try {
      setEsito(await checkUpdates());
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setInCorso(false);
    }
  };

  return (
    <div className="border border-border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-fg">
          {versione ? t.settings.versionCurrent(versione) : "—"}
        </span>
        <Button size="sm" variant="outline" disabled={inCorso} onClick={controlla}>
          {inCorso ? t.settings.versionChecking : t.settings.versionCheck}
        </Button>
      </div>

      {errore && <p className="mt-3 text-xs text-danger">{errore}</p>}

      {esito && !esito.update_available && (
        <p className="mt-3 text-xs text-muted">{t.settings.versionUpToDate}</p>
      )}

      {esito?.update_available && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-sm text-fg-strong">{t.settings.versionAvailable(esito.latest ?? "")}</p>
          {esito.notes && (
            <>
              <p className="mt-2 text-[10px] uppercase tracking-wider text-faint">
                {t.settings.versionNotesHeading}
              </p>
              {/* Testo di GitHub, non nostro: si mostra come citazione. */}
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap border-l-2 border-border pl-3 text-xs text-muted">
                {esito.notes}
              </pre>
            </>
          )}
          {esito.url && (
            <a href={esito.url} target="_blank" rel="noreferrer" className="mt-2 inline-block">
              <Button size="sm" variant="outline">
                <ExternalLink size={14} /> {t.settings.versionOpenRelease}
              </Button>
            </a>
          )}
        </div>
      )}
    </div>
  );
}
