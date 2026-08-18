"use client";

import { useState } from "react";
import {
  errText, patchConfigSettings, pickPath, type ConfigSettings,
} from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Campo di configurazione in chiaro (percorso o URL), con il dialog nativo
   dove è disponibile. Salva sul blur: un bottone Salva per campo, in una
   procedura a passi, aggiunge un gesto senza aggiungere informazione.
   Condiviso fra il passo libreria e il passo slskd. */
export type PathFieldKey = "library_root" | "archive_root" | "slskd_download_dir" | "slskd_url";

export function PathField({ fieldKey, label, value, detail, canPick, kind = "folder", onSaved }: {
  fieldKey: PathFieldKey;
  label: string;
  value: string;
  detail?: string | null;
  canPick: boolean;
  kind?: "folder" | "text";
  onSaved: (config: ConfigSettings) => void;
}) {
  const t = useT();
  const [error, setError] = useState<string | null>(null);

  const salva = async (next: string) => {
    if (next === value) return; // niente PATCH inutili a ogni blur
    try {
      onSaved(await patchConfigSettings({ [fieldKey]: next }));
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  };

  const scegli = async () => {
    const { path } = await pickPath("folder", value || undefined);
    if (path) await salva(path);
  };

  return (
    <div>
      <label className="mb-1 block text-xs uppercase tracking-wider text-muted">{label}</label>
      <div className="flex gap-2">
        <Input
          defaultValue={value}
          onBlur={(e) => salva(e.target.value.trim())}
          className="flex-1"
        />
        {kind === "folder" && canPick && (
          <Button size="sm" variant="outline" onClick={scegli}>{t.setup.choose}</Button>
        )}
      </div>
      {detail && <p className="mt-1 text-xs text-faint">{detail}</p>}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
