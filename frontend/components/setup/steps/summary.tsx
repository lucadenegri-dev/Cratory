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
    getProbe(true).then((r) => setComponents(r.components)).catch(() => setComponents([]));
    servicesStatus().then((r) => setServices(r.services)).catch(() => setServices([]));
  }, []);

  if (!components || !services) return <Loading />;

  const righe = [
    ...components.map((c) => ({ key: c.key, on: c.present })),
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
