"use client";

import { useEffect, useState } from "react";
import { pickerAvailability, pickPath } from "@/lib/api";
import { Button, Spinner } from "./ui";
import { useT } from "@/lib/i18n";

/** Disponibilità del dialog nativo: fetch una volta al mount, errore = false
 *  (i pulsanti Sfoglia semplicemente non compaiono). */
export function usePickerAvailability(): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    pickerAvailability().then((r) => setOk(r.available)).catch(() => setOk(false));
  }, []);
  return ok;
}

/* Apre il dialog nativo del backend (macOS) e riporta il percorso scelto.
   Il genitore decide se montarlo (usePickerAvailability) e cosa farne: qui
   niente salvataggio, solo la scelta. type="button": il pulsante può vivere
   dentro form senza scatenarne il submit. */
export function PathPickerButton({ kind, start, prompt, onPick, onError }: {
  kind: "folder" | "file";
  start?: string;
  prompt?: string;
  onPick: (path: string) => void;
  onError: (message: string) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try {
      const r = await pickPath(kind, start, prompt);
      if (r.path) onPick(r.path);
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" size="sm" onClick={open} disabled={busy}>
      {busy ? <Spinner /> : t.common.browseButton}
    </Button>
  );
}
