"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errText, getInstallStatus, getProbe, startInstall, type ProbeComponent } from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { ComponentRow } from "../component-row";

// Un componente per cui l'installazione composita è finita in errore, col
// motivo per mostrarlo (fix 1): prima il giro si limitava a smettere di
// aspettare quando lo stato tornava "error", senza dire nulla — la riga
// restava su "non trovato" e l'utente non aveva alcun indizio del perché.
type InstallFailure = { key: string; message: string | null; errorCode?: string | null };

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
  const [failures, setFailures] = useState<InstallFailure[]>([]);

  // Come mounted/busy in ComponentRow: se lo step si smonta a metà del giro
  // composito (l'utente naviga via — es. il bottone Configura della riga
  // demone, che non guardava `disabled`, fix 2), il giro deve smettere sia di
  // chiamare setState sia di avviare altri install. Senza questo continua a
  // parlare col backend senza che nessuna UI lo osservi, e rientrando nello
  // step si trovano i bottoni sbloccati mentre un job fantasma gira ancora
  // (409 inspiegabile al primo click).
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

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
    setFailures([]);
    const fallite: InstallFailure[] = [];
    try {
      for (const c of mancanti) {
        if (!mounted.current) return;
        try {
          await startInstall(c.key);
        } catch (e) {
          // Avviare il job può fallire (409, rete): registra il motivo e
          // prosegui con il prossimo componente invece di fermare tutto.
          // Sono job indipendenti — quello di questo componente che non è
          // partito non dice nulla sulla riuscita degli altri.
          fallite.push({ key: c.key, message: errText(e) });
          continue;
        }
        if (!mounted.current) return;
        let status = await getInstallStatus();
        while (mounted.current && status.status === "running") {
          await new Promise((r) => setTimeout(r, 1000));
          if (!mounted.current) break;
          status = await getInstallStatus();
        }
        if (!mounted.current) return;
        if (status.status === "error") {
          // Stessa scelta: un componente fallito non blocca i successivi.
          fallite.push({ key: c.key, message: status.detail, errorCode: status.error_code });
        }
      }
    } finally {
      if (mounted.current) {
        setBusyKey(null);
        setFailures(fallite);
        load(true);
      }
    }
  };

  const componentLabel = (key: string) =>
    t.setup.components[key as keyof typeof t.setup.components] ?? key;

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
          {failures.length > 0 && (
            <Alert tone="danger">
              <ul className="space-y-1.5">
                {failures.map((f) => (
                  <li key={f.key}>
                    <p>{t.setup.installAllFailedFor(componentLabel(f.key))}</p>
                    {/* checksum_mismatch e unsafe_archive sono un allarme, non un
                        intoppo (design doc §7): stessa distinzione di ComponentRow. */}
                    {f.errorCode === "checksum_mismatch" && (
                      <p className="mt-0.5 text-xs text-danger">{t.setup.installFailedChecksum}</p>
                    )}
                    {f.errorCode === "unsafe_archive" && (
                      <p className="mt-0.5 text-xs text-danger">{t.setup.installFailedArchive}</p>
                    )}
                    {/* Dettaglio grezzo del backend, come nota secondaria — stesso
                        pattern del fallimento a riga singola in ComponentRow. */}
                    {f.message && <p className="mt-0.5 text-[11px] text-faint">{f.message}</p>}
                  </li>
                ))}
              </ul>
            </Alert>
          )}
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
