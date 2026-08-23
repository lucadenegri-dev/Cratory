"use client";

import { useEffect, useState } from "react";
import { getAppVersion } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useAggiornamento } from "@/lib/updates";
import { AggiornamentoBrowser } from "./aggiornamento-browser";
import { AggiornamentoGuscio } from "./aggiornamento-guscio";

/* La versione in uso, e chi si occupa degli aggiornamenti.

   Due mondi, non due rami sparsi: nel guscio desktop c'è qualcosa da
   installare e se ne occupa AggiornamentoGuscio; nel browser di sviluppo non
   c'è, e resta il bottone che interroga il backend. La versione la legge
   questo componente, una volta sola, e la passa a chi dei due viene montato. */
export function VersionCard() {
  const t = useT();
  const [versione, setVersione] = useState<string | null>(null);
  const { nelGuscio } = useAggiornamento();

  useEffect(() => {
    getAppVersion().then((r) => setVersione(r.version)).catch(() => setVersione(null));
  }, []);

  const etichetta = versione ? t.settings.versionCurrent(versione) : "—";

  return (
    <div className="border border-border p-5">
      {nelGuscio ? (
        <AggiornamentoGuscio versione={etichetta} />
      ) : (
        <AggiornamentoBrowser versione={etichetta} />
      )}
    </div>
  );
}
