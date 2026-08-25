"use client";

import { useEffect, useState } from "react";
import { getProbe, servicesStatus, type ProbeComponent, type ServiceStatus } from "@/lib/api";
import { Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Il riepilogo non è decorativo: è l'elenco di cosa resta spento e perché,
   che è la domanda che l'utente si farà al primo uso. */
export function SummaryStep() {
  const t = useT();
  const [components, setComponents] = useState<ProbeComponent[] | null>(null);
  const [services, setServices] = useState<ServiceStatus[] | null>(null);

  useEffect(() => {
    // Niente force=true: rilanciare l'intero probe (5 sottoprocessi, import
    // di Essentia incluso) ad ogni render dell'ultimo passo non serve — il
    // backend tiene già una cache breve, e chi ha appena installato qualcosa
    // al passo 1 ha già premuto "Ricontrolla" lì.
    getProbe(false).then((r) => setComponents(r.components)).catch(() => setComponents([]));
    servicesStatus().then((r) => setServices(r.services)).catch(() => setServices([]));
  }, []);

  if (!components || !services) return <Loading />;

  // slskd compare in entrambe le fonti — una volta come componente del probe
  // (chiave grezza "slskd", stato "present" = il demone risponde davvero),
  // una volta come servizio (nome comprensibile "slskd (Soulseek)", stato
  // "configured" = URL e cartella scritti). Stessa cosa vista da due
  // angolazioni, non due voci: una riga sola, col nome leggibile del
  // servizio e lo stato del probe. Si sceglie `present` e non `configured`
  // perché è il segnale più vero di "funziona adesso" — dopo il fix che fa
  // ricadere il probe sull'indirizzo di default, `present` è true anche per
  // un demone già acceso ma non ancora configurato, mentre `configured`
  // direbbe "spento" proprio nel caso che quel fix esiste per riconoscere.
  /* Niente piu' de-duplica fra le due liste: serviva a slskd, che compariva
     sia fra i componenti sia fra i servizi. Adesso e' solo un servizio, e un
     componente non puo' piu' essere anche un servizio. */
  const righe = [
    ...components.map((c) => {
      const servizio = services.find((s) => s.key === c.key);
      return { key: servizio ? servizio.name : c.key, on: c.present };
    }),
    ...services.map((s) => ({ key: s.name, on: s.configured })),
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.summaryBody}</p>
      <div className="border border-border">
        {righe.map((r) => (
          <div key={r.key} className="flex items-center justify-between border-b border-border px-4 py-2 last:border-0">
            <span className="text-sm text-fg">{r.key}</span>
            <span className={`text-[10px] uppercase tracking-wider ${r.on ? "text-fg-strong" : "text-muted"}`}>
              {r.on ? t.setup.summaryOn : t.setup.summaryOff}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
