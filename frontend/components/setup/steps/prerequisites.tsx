"use client";

import { useCallback, useEffect, useState } from "react";
import { errText, getInstallStatus, getProbe, startInstall, type ProbeComponent } from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { ComponentRow } from "../component-row";

export function PrerequisitesStep({ onGoToSlskd }: { onGoToSlskd: () => void }) {
  const t = useT();
  const [components, setComponents] = useState<ProbeComponent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Chiave del componente che sta installando, se ce n'è uno: il backend
  // esegue un job alla volta (409 altrimenti), quindi finché una riga è
  // occupata tutti i bottoni Installa delle altre righe restano disabilitati.
  // Niente polling qui: ogni ComponentRow riporta i propri cambi di stato
  // tramite onBusyChange, riusando il polling che già fa per conto suo.
  // "__tutti__" è il valore usato mentre gira l'installazione sequenziale
  // del bottone qui sotto: nessuna singola riga la possiede.
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const load = useCallback((force = false) => {
    getProbe(force)
      .then((r) => { setComponents(r.components); setError(null); })
      .catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => load(), [load]);

  // Solo ciò che manca davvero E per cui esiste una build: ffmpeg su
  // piattaforme senza binario resta manuale, il demone slskd rimanda al suo
  // passo (onConfigure), mai un install alla cieca.
  const mancanti = (components ?? []).filter(
    (c) => !c.present && c.installable && c.kind !== "daemon",
  );

  const installaTutto = async () => {
    // In sequenza, non in parallelo: il backend esegue un job alla volta e
    // risponderebbe 409 al secondo. Lo stesso lucchetto che disabilita i
    // bottoni delle righe vale qui.
    setBusyKey("__tutti__");
    try {
      for (const c of mancanti) {
        await startInstall(c.key);
        while ((await getInstallStatus()).status === "running") {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    } finally {
      setBusyKey(null);
      load(true);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.prereqBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      {components ? (
        <>
          <Button size="sm" variant="outline"
                  disabled={mancanti.length === 0 || busyKey !== null}
                  onClick={installaTutto}>
            {t.setup.installAllMissing}
          </Button>
          <div className="border border-border">
            {components.map((c) => (
              <ComponentRow
                key={c.key}
                c={c}
                onChanged={() => load(true)}
                disabled={busyKey !== null && busyKey !== c.key}
                onBusyChange={(busy) => setBusyKey(busy ? c.key : null)}
                onConfigure={onGoToSlskd}
              />
            ))}
          </div>
          <Button size="sm" variant="ghost" onClick={() => load(true)}>{t.setup.recheck}</Button>
        </>
      ) : (
        !error && <Loading />
      )}
    </div>
  );
}
