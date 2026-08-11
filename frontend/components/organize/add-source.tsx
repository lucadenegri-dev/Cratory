"use client";

import { useState } from "react";
import { addSource } from "@/lib/organize/api";
import { Button, Input, Spinner } from "./ui";
import { useT } from "@/lib/organize/i18n";
import { PathPickerButton, usePickerAvailability } from "./path-picker-button";

export function AddSource({ onAdded }: { onAdded: () => void }) {
  const t = useT();
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pickerOk = usePickerAvailability();

  const submit = async () => {
    if (!path.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addSource(path.trim(), label.trim() || undefined);
      setPath("");
      setLabel("");
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.sources.addRoot}</div>
      {/* path su riga propria a piena larghezza: dev'essere leggibile per intero */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={t.sources.pathPlaceholder}
            className="flex-1"
          />
          {pickerOk && (
            <PathPickerButton kind="folder" start={path} prompt={t.sources.addRoot}
              onPick={(p) => { setError(null); setPath(p); }} onError={setError} />
          )}
        </div>
        <div className="flex gap-2">
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={t.sources.labelPlaceholder}
            className="flex-1"
          />
          <Button onClick={submit} disabled={busy || !path.trim()}>{busy ? <Spinner /> : t.sources.addButton}</Button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
