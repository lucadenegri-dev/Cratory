"use client";

import { useCallback, useEffect, useState } from "react";
import { errText, getProbe, type ProbeComponent } from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { ComponentRow } from "../component-row";

export function PrerequisitesStep() {
  const t = useT();
  const [components, setComponents] = useState<ProbeComponent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((force = false) => {
    getProbe(force)
      .then((r) => { setComponents(r.components); setError(null); })
      .catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => load(), [load]);

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.prereqBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      {components ? (
        <>
          <div className="border border-border">
            {components.map((c) => (
              <ComponentRow key={c.key} c={c} onChanged={() => load(true)} />
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
