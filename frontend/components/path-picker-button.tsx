"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { errText, pickerAvailability, pickPath } from "@/lib/api";
import { Button, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Disponibilità del dialog nativo: fetch una volta al mount, errore = false
 *  (i pulsanti Sfoglia semplicemente non compaiono). Condiviso da Settings e
 *  dalla modale "Collega file locale". */
export function usePickerAvailability(): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    pickerAvailability().then((r) => setOk(r.available)).catch(() => setOk(false));
  }, []);
  return ok;
}

/* Apre il dialog nativo del backend (macOS) e riporta il percorso scelto.
   Il genitore decide se montarlo (usePickerAvailability) e cosa farne: qui
   niente salvataggio, solo la scelta. type="button": il pulsante vive anche
   dentro form (modale link file) e non deve scatenarne il submit. */
export function PathPickerButton({ kind, start, prompt, defaultName, label, variant = "primary", onPick, onError }: {
  kind: "folder" | "file" | "save";
  start?: string;
  prompt?: string;
  defaultName?: string;
  /** Testo del pulsante; default «Sfoglia…». */
  label?: ReactNode;
  variant?: "primary" | "outline";
  onPick: (path: string) => void;
  onError: (message: string) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try {
      const r = await pickPath(kind, start, prompt, defaultName);
      if (r.path) onPick(r.path);
    } catch (e) {
      onError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" size="sm" variant={variant} onClick={open} disabled={busy}>
      {busy ? <Spinner /> : (label ?? t.settings.browseButton)}
    </Button>
  );
}
