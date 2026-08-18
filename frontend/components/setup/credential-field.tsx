"use client";

import { useState } from "react";
import { patchConfigSettings, errText, type SecretKey, type SecretState } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Un campo credenziale. Non pre-riempie MAI l'input: il backend non manda il
   valore, e mostrare un finto valore mascherato dentro un campo editabile
   farebbe credere di poterlo leggere. Chiave presente = riga di stato + link
   "sostituisci"; chiave assente = input vuoto. */
export function CredentialField({ fieldKey, label, state, onSaved }: {
  fieldKey: SecretKey;
  label: string;
  state: SecretState | undefined;
  onSaved: () => void;
}) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const configured = state?.configured ?? false;

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await patchConfigSettings({ [fieldKey]: value });
      setValue("");
      setEditing(false);
      onSaved();
    } catch (e) {
      setError(errText(e));
    } finally {
      setSaving(false);
    }
  };

  if (configured && !editing) {
    return (
      <div className="flex flex-wrap items-center gap-2 py-1.5">
        <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
        <span className="text-xs text-fg-strong">{t.setup.configuredAs(state?.hint ?? "")}</span>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-xs text-fg underline-offset-4 hover:underline"
        >
          {t.setup.replace}
        </button>
      </div>
    );
  }

  return (
    <div className="py-1.5">
      <label className="mb-1 block text-xs uppercase tracking-wider text-muted">{label}</label>
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          className="flex-1"
        />
        <Button size="sm" variant="outline" disabled={saving || !value.trim()} onClick={save}>
          {t.setup.save}
        </Button>
      </div>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
